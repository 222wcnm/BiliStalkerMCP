import logging
import asyncio
import time
from typing import Any, Literal

from async_lru import alru_cache
from bilibili_api import Credential, aid2bvid, article, search, user, video
from bilibili_api.exceptions import ApiException

from ..config import DEFAULT_HEADERS
from ..infra.http_client import get_shared_http_client
from ..models import (
    ArticleContentResponse,
    ArticleListItem,
    ArticleStatsResponse,
    ArticlesResponse,
    FollowingItemResponse,
    FollowingsResponse,
    SubtitleResponse,
    SubtitleTrack,
    UserInfoResponse,
    VideoDetailItem,
    VideoDetailResponse,
    VideoListItem,
    VideoListResponse,
    VideoStatResponse,
)
from ..observability import add_upstream_duration_ms, record_cache_hit
from ..parsers.dynamic_parser import format_timestamp
from ..retry import RetryableBiliApiError, with_retry

logger = logging.getLogger(__name__)
SUBTITLE_FETCH_CONCURRENCY = 4
DEFAULT_SUBTITLE_MODE = "smart"
DEFAULT_SUBTITLE_LANG = "auto"
DEFAULT_SUBTITLE_MAX_CHARS = 12000
DEFAULT_SUBTITLE_LANGUAGE_PRIORITY = (
    "zh-cn",
    "zh-hans",
    "zh-hant",
    "ai-zh",
    "en-us",
    "en",
    "ai-en",
)


async def _timed_await(awaitable: Any) -> Any:
    started = time.perf_counter()
    result = await awaitable
    add_upstream_duration_ms((time.perf_counter() - started) * 1000)
    return result


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _safe_aid_to_bvid(aid: Any) -> str | None:
    if not aid:
        return None
    try:
        return aid2bvid(aid)
    except Exception:
        return None


def _cache_hit(before: Any, after: Any) -> bool:
    return (after.hits > before.hits) if before and after else False


def _build_cookie_header(cred: Credential | None) -> str:
    if cred is None or not hasattr(cred, "get_cookies"):
        return ""
    try:
        cookies = cred.get_cookies() or {}
        return "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    except Exception:
        return ""


def _normalize_subtitle_url(subtitle_url: Any) -> str | None:
    if not subtitle_url or not isinstance(subtitle_url, str):
        return None

    value = subtitle_url.strip()
    if not value:
        return None

    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value.lstrip('/')}"


async def _fetch_subtitle_text(
    subtitle_url: Any,
    cred: Credential | None,
) -> tuple[str, str | None]:
    url = _normalize_subtitle_url(subtitle_url)
    if not url:
        return "", "subtitle_url missing"

    headers = DEFAULT_HEADERS.copy()
    cookie = _build_cookie_header(cred)
    if cookie:
        headers["Cookie"] = cookie

    try:
        started = time.perf_counter()
        response = await get_shared_http_client().get(url, headers=headers)
        add_upstream_duration_ms((time.perf_counter() - started) * 1000)

        response.raise_for_status()
        subtitle_payload = response.json()

        body = subtitle_payload.get("body") or []
        lines: list[str] = []
        for item in body:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                lines.append(content.strip())

        return "\n".join(lines), None
    except Exception as exc:
        return "", str(exc)


def _extract_tags(video_info: dict[str, Any]) -> list[str]:
    raw_tags = video_info.get("tag") or video_info.get("tags") or []
    if not isinstance(raw_tags, list):
        return []

    tags: list[str] = []
    for item in raw_tags:
        if isinstance(item, str) and item.strip():
            tags.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue

        tag_name = item.get("tag_name") or item.get("name")
        if isinstance(tag_name, str) and tag_name.strip():
            tags.append(tag_name.strip())

    return tags


def _select_video_review_count(video_data: dict[str, Any]) -> int | None:
    """Pick the best available engagement counter for list-level `review`."""
    candidates = (
        _coerce_int(video_data.get("review")),
        _coerce_int(video_data.get("video_review")),
        _coerce_int(video_data.get("comment")),
    )

    for value in candidates:
        if value is not None and value > 0:
            return value

    for value in candidates:
        if value is not None:
            return value

    return None


def _normalize_language_tag(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def _build_track_metadata(
    cid: int,
    part: str | None,
    subtitle_item: dict[str, Any],
) -> tuple[SubtitleTrack, str | None]:
    lan = subtitle_item.get("lan") if isinstance(subtitle_item.get("lan"), str) else None
    lan_doc = (
        subtitle_item.get("lan_doc")
        if isinstance(subtitle_item.get("lan_doc"), str)
        else None
    )

    is_ai_generated = bool(
        (isinstance(lan, str) and lan.startswith("ai-"))
        or (_coerce_int(subtitle_item.get("ai_type")) or 0) > 0
        or (_coerce_int(subtitle_item.get("ai_status")) or 0) > 0
    )

    track = SubtitleTrack(
        cid=cid,
        part=part,
        lan=lan,
        lan_doc=lan_doc,
        is_ai_generated=is_ai_generated,
        text="",
    )
    subtitle_url = subtitle_item.get("subtitle_url")
    return track, subtitle_url


def _append_track_with_budget(
    track: SubtitleTrack,
    raw_text: str,
    selected_tracks: list[SubtitleTrack],
    full_text_lines: list[str],
    remaining_budget: int,
) -> tuple[int, bool]:
    text = raw_text or ""
    was_truncated = False
    if text:
        separator_cost = 1 if full_text_lines else 0
        if remaining_budget <= separator_cost:
            text = ""
            was_truncated = True
        else:
            remaining_budget -= separator_cost
            if len(text) > remaining_budget:
                text = text[:remaining_budget]
                remaining_budget = 0
                was_truncated = True
            else:
                remaining_budget -= len(text)

    selected_tracks.append(track.model_copy(update={"text": text}))
    if text:
        full_text_lines.append(text)
    return remaining_budget, was_truncated


def _select_smart_subtitle_candidate(
    candidates: list[dict[str, Any]],
    requested_language: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if not candidates:
        return None, None

    requested_raw = requested_language.strip() if isinstance(requested_language, str) else ""
    requested_norm = _normalize_language_tag(requested_raw)
    normalized_auto = _normalize_language_tag(DEFAULT_SUBTITLE_LANG)

    if requested_norm and requested_norm != normalized_auto:
        for candidate in candidates:
            lan_norm = _normalize_language_tag(candidate["track"].lan)
            if lan_norm == requested_norm:
                return candidate, None

        for candidate in candidates:
            lan_norm = _normalize_language_tag(candidate["track"].lan)
            if lan_norm and (
                lan_norm.startswith(f"{requested_norm}-")
                or requested_norm.startswith(f"{lan_norm}-")
            ):
                selected = candidate["track"].lan or "unknown"
                return (
                    candidate,
                    f"requested '{requested_raw}' not exact; matched '{selected}'",
                )

    for preferred in DEFAULT_SUBTITLE_LANGUAGE_PRIORITY:
        for candidate in candidates:
            lan_norm = _normalize_language_tag(candidate["track"].lan)
            if lan_norm == preferred:
                if requested_norm and requested_norm != normalized_auto:
                    selected = candidate["track"].lan or "unknown"
                    return (
                        candidate,
                        f"requested '{requested_raw}' unavailable; fallback to '{selected}'",
                    )
                return candidate, None

    fallback_candidate = candidates[0]
    selected = fallback_candidate["track"].lan or "unknown"
    if requested_norm and requested_norm != normalized_auto:
        return (
            fallback_candidate,
            f"requested '{requested_raw}' unavailable; fallback to '{selected}'",
        )
    return fallback_candidate, "auto preference not matched; fallback to first available"


async def _collect_subtitles(
    video_client: video.Video,
    pages: list[dict[str, Any]],
    cred: Credential | None,
    subtitle_mode: Literal["minimal", "smart", "full"] = DEFAULT_SUBTITLE_MODE,
    subtitle_lang: str = DEFAULT_SUBTITLE_LANG,
    subtitle_max_chars: int = DEFAULT_SUBTITLE_MAX_CHARS,
) -> SubtitleResponse:
    mode = subtitle_mode.strip().lower() if isinstance(subtitle_mode, str) else ""
    if mode == "minimal":
        normalized_mode: Literal["minimal", "smart", "full"] = "minimal"
    elif mode == "full":
        normalized_mode = "full"
    else:
        normalized_mode = "smart"

    if normalized_mode == "minimal":
        return SubtitleResponse(
            enabled=True,
            mode=normalized_mode,
            requested_language=subtitle_lang if isinstance(subtitle_lang, str) else DEFAULT_SUBTITLE_LANG,
            available_languages=[],
            selected_language=None,
            fallback_reason="subtitle metadata and text skipped by mode=minimal",
            truncated=False,
            returned_chars=0,
            dropped_tracks=0,
            track_count=0,
            tracks=[],
            full_text="",
            errors=[],
        )

    char_budget = (
        subtitle_max_chars
        if isinstance(subtitle_max_chars, int)
        else DEFAULT_SUBTITLE_MAX_CHARS
    )
    if char_budget < 1:
        char_budget = DEFAULT_SUBTITLE_MAX_CHARS

    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    semaphore = asyncio.Semaphore(SUBTITLE_FETCH_CONCURRENCY)

    async def _timed_get_subtitle(cid: int) -> dict[str, Any]:
        async with semaphore:
            return await _timed_await(video_client.get_subtitle(cid=cid))

    async def _timed_fetch_track_text(subtitle_url: Any) -> tuple[str, str | None]:
        async with semaphore:
            return await _fetch_subtitle_text(subtitle_url, cred)

    async def _collect_page_tracks(
        page: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        page_tracks: list[dict[str, Any]] = []
        page_errors: list[str] = []

        cid = _coerce_int(page.get("cid"))
        part = page.get("part")
        part_value = part if isinstance(part, str) else None

        if cid is None:
            page_errors.append("page without cid")
            return page_tracks, page_errors

        try:
            subtitle_data = await _timed_get_subtitle(cid)
        except Exception as exc:
            page_errors.append(f"cid {cid}: subtitle metadata failed: {exc}")
            return page_tracks, page_errors

        subtitle_items = (subtitle_data or {}).get("subtitles") or []
        if not isinstance(subtitle_items, list):
            page_errors.append(f"cid {cid}: invalid subtitle payload")
            return page_tracks, page_errors

        for subtitle_item in subtitle_items:
            if not isinstance(subtitle_item, dict):
                continue
            track, subtitle_url = _build_track_metadata(
                cid=cid,
                part=part_value,
                subtitle_item=subtitle_item,
            )
            page_tracks.append({"track": track, "subtitle_url": subtitle_url})

        return page_tracks, page_errors

    page_tasks = [_collect_page_tracks(page) for page in pages]
    for page_tracks, page_errors in await asyncio.gather(*page_tasks):
        candidates.extend(page_tracks)
        errors.extend(page_errors)

    available_languages: list[str] = []
    seen_languages: set[str] = set()
    for candidate in candidates:
        lan = candidate["track"].lan
        lan_norm = _normalize_language_tag(lan)
        if not lan_norm or lan_norm in seen_languages:
            continue
        seen_languages.add(lan_norm)
        available_languages.append(lan or lan_norm)

    if not candidates:
        return SubtitleResponse(
            enabled=True,
            mode=normalized_mode,
            requested_language=subtitle_lang if isinstance(subtitle_lang, str) else DEFAULT_SUBTITLE_LANG,
            available_languages=available_languages,
            selected_language=None,
            fallback_reason="No subtitle tracks available",
            truncated=False,
            returned_chars=0,
            dropped_tracks=0,
            track_count=0,
            tracks=[],
            full_text="",
            errors=errors,
        )

    selected_tracks: list[SubtitleTrack] = []
    full_text_lines: list[str] = []
    truncated = False
    dropped_tracks = 0
    selected_language: str | None = None
    fallback_reason: str | None = None

    if normalized_mode == "smart":
        selected_candidate, fallback_reason = _select_smart_subtitle_candidate(
            candidates=candidates,
            requested_language=subtitle_lang,
        )
        if selected_candidate is None:
            return SubtitleResponse(
                enabled=True,
                mode=normalized_mode,
                requested_language=subtitle_lang if isinstance(subtitle_lang, str) else DEFAULT_SUBTITLE_LANG,
                available_languages=available_languages,
                selected_language=None,
                fallback_reason="No subtitle tracks available",
                truncated=False,
                returned_chars=0,
                dropped_tracks=0,
                track_count=0,
                tracks=[],
                full_text="",
                errors=errors,
            )

        text, error = await _timed_fetch_track_text(selected_candidate["subtitle_url"])
        if error:
            track = selected_candidate["track"]
            errors.append(
                f"cid {track.cid} {track.lan_doc or track.lan or 'unknown'}: {error}"
            )

        remaining_budget = char_budget
        remaining_budget, was_truncated = _append_track_with_budget(
            track=selected_candidate["track"],
            raw_text=text,
            selected_tracks=selected_tracks,
            full_text_lines=full_text_lines,
            remaining_budget=remaining_budget,
        )
        _ = remaining_budget
        truncated = truncated or was_truncated
        dropped_tracks = max(0, len(candidates) - len(selected_tracks))
        selected_language = selected_candidate["track"].lan
    else:
        track_tasks = [
            _timed_fetch_track_text(candidate["subtitle_url"]) for candidate in candidates
        ]
        track_results = await asyncio.gather(*track_tasks)
        remaining_budget = char_budget
        for candidate, (text, error) in zip(candidates, track_results):
            track = candidate["track"]
            if error:
                errors.append(
                    f"cid {track.cid} {track.lan_doc or track.lan or 'unknown'}: {error}"
                )
            remaining_budget, was_truncated = _append_track_with_budget(
                track=track,
                raw_text=text,
                selected_tracks=selected_tracks,
                full_text_lines=full_text_lines,
                remaining_budget=remaining_budget,
            )
            truncated = truncated or was_truncated
        dropped_tracks = max(0, len(candidates) - len(selected_tracks))

    full_text = "\n".join(full_text_lines)

    return SubtitleResponse(
        enabled=True,
        mode=normalized_mode,
        requested_language=subtitle_lang if isinstance(subtitle_lang, str) else DEFAULT_SUBTITLE_LANG,
        available_languages=available_languages,
        selected_language=selected_language,
        fallback_reason=fallback_reason,
        truncated=truncated,
        returned_chars=len(full_text),
        dropped_tracks=dropped_tracks,
        track_count=len(selected_tracks),
        tracks=selected_tracks,
        full_text=full_text,
        errors=errors,
    )


@alru_cache(maxsize=128, ttl=3600)
@with_retry(max_retries=5, base_delay=2.0, return_default=True, default_on_exhaust=None)
async def _get_user_id_by_username_cached(username: str) -> int | None:
    if not username:
        return None

    search_result = await _timed_await(
        search.search_by_type(
            keyword=username,
            search_type=search.SearchObjectType.USER,
        )
    )
    result_list = search_result.get("result") or (search_result.get("data") or {}).get(
        "result"
    )

    if not isinstance(result_list, list) or not result_list:
        logger.warning("User '%s' not found in search results", username)
        return None

    username_lower = username.lower()
    for user_item in result_list:
        uname = (user_item.get("uname") or "").lower()
        if uname == username_lower:
            return user_item.get("mid")

    logger.warning(
        "No exact match for '%s', using first result '%s'",
        username,
        result_list[0].get("uname"),
    )
    return result_list[0].get("mid")


async def get_user_id_by_username(username: str) -> int | None:
    before = _get_user_id_by_username_cached.cache_info()
    result = await _get_user_id_by_username_cached(username)
    after = _get_user_id_by_username_cached.cache_info()
    record_cache_hit("user_id_by_username", _cache_hit(before, after))
    return result


@alru_cache(maxsize=32, ttl=300)
@with_retry(max_retries=3, base_delay=2.0)
async def _fetch_user_info_cached(user_id: int, cred: Credential) -> dict[str, Any]:
    u = user.User(uid=user_id, credential=cred)
    info = await _timed_await(u.get_user_info())
    if not info or "mid" not in info:
        raise ValueError(f"Invalid response for user {user_id}")

    user_data = {
        "mid": info.get("mid"),
        "name": info.get("name"),
        "sign": info.get("sign"),
        "following": None,
        "follower": None,
    }

    try:
        stat_url = "https://api.bilibili.com/x/relation/stat"
        params = {"vmid": user_id}
        headers = DEFAULT_HEADERS.copy()
        cookie = _build_cookie_header(cred)
        if cookie:
            headers["Cookie"] = cookie

        stat_started = time.perf_counter()
        response = await get_shared_http_client().get(
            stat_url,
            params=params,
            headers=headers,
        )
        add_upstream_duration_ms((time.perf_counter() - stat_started) * 1000)

        response.raise_for_status()
        stat_data = response.json()

        if stat_data.get("code") == 0 and "data" in stat_data:
            user_data["following"] = stat_data["data"].get("following")
            user_data["follower"] = stat_data["data"].get("follower")
        else:
            logger.warning(
                "Failed to get relation stat for uid %s: %s",
                user_id,
                stat_data.get("message"),
            )
    except Exception as exc:
        logger.warning("Relation stat request failed for uid %s: %s", user_id, exc)

    return user_data


async def fetch_user_info(user_id: int, cred: Credential) -> dict[str, Any]:
    before = _fetch_user_info_cached.cache_info()
    user_data = await _fetch_user_info_cached(user_id, cred)
    after = _fetch_user_info_cached.cache_info()
    record_cache_hit("user_info", _cache_hit(before, after))

    payload = UserInfoResponse(**user_data)
    return payload.model_dump()


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_user_videos(
    user_id: int,
    page: int,
    limit: int,
    cred: Credential,
) -> dict[str, Any]:
    u = user.User(uid=user_id, credential=cred)
    video_list = await _timed_await(u.get_videos(pn=page, ps=limit))
    raw_videos = (video_list.get("list") or {}).get("vlist") or []

    videos = []
    for video_data in raw_videos:
        videos.append(
            VideoListItem(
                bvid=video_data.get("bvid") or _safe_aid_to_bvid(video_data.get("aid")),
                aid=_coerce_int(video_data.get("aid")),
                title=video_data.get("title"),
                description=video_data.get("description"),
                author=video_data.get("author"),
                length=video_data.get("length"),
                created_time=format_timestamp(_coerce_int(video_data.get("created"))),
                play=_coerce_int(video_data.get("play")),
                review=_select_video_review_count(video_data),
            )
        )

    payload = VideoListResponse(
        videos=videos,
        total=_coerce_int((video_list.get("page") or {}).get("count")) or 0,
    )
    return payload.model_dump()


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_video_detail(
    bvid: str,
    fetch_subtitles: bool = False,
    cred: Credential | None = None,
    *,
    subtitle_mode: Literal["minimal", "smart", "full"] = DEFAULT_SUBTITLE_MODE,
    subtitle_lang: str = DEFAULT_SUBTITLE_LANG,
    subtitle_max_chars: int = DEFAULT_SUBTITLE_MAX_CHARS,
) -> dict[str, Any]:
    v = video.Video(bvid=bvid, credential=cred)

    video_info = await _timed_await(v.get_info())
    pages_raw = await _timed_await(v.get_pages())

    normalized_pages: list[dict[str, Any]] = []
    if isinstance(pages_raw, list):
        for page in pages_raw:
            if not isinstance(page, dict):
                continue
            normalized_pages.append(
                {
                    "cid": _coerce_int(page.get("cid")),
                    "page": _coerce_int(page.get("page")),
                    "part": page.get("part"),
                    "duration": _coerce_int(page.get("duration")),
                }
            )

    stat = video_info.get("stat") if isinstance(video_info, dict) else {}
    if not isinstance(stat, dict):
        stat = {}

    video_item = VideoDetailItem(
        bvid=(video_info.get("bvid") if isinstance(video_info, dict) else None) or bvid,
        aid=_coerce_int(video_info.get("aid") if isinstance(video_info, dict) else None),
        title=video_info.get("title") if isinstance(video_info, dict) else None,
        desc=video_info.get("desc") if isinstance(video_info, dict) else None,
        publish_time=format_timestamp(
            _coerce_int(video_info.get("pubdate") if isinstance(video_info, dict) else None)
        ),
        stat=VideoStatResponse(
            view=_coerce_int(stat.get("view")),
            danmaku=_coerce_int(stat.get("danmaku")),
            reply=_coerce_int(stat.get("reply")),
            favorite=_coerce_int(stat.get("favorite")),
            coin=_coerce_int(stat.get("coin")),
            share=_coerce_int(stat.get("share")),
            like=_coerce_int(stat.get("like")),
        ),
        tags=_extract_tags(video_info if isinstance(video_info, dict) else {}),
        pages=normalized_pages,
    )

    if fetch_subtitles:
        subtitles = await _collect_subtitles(
            v,
            normalized_pages,
            cred,
            subtitle_mode=subtitle_mode,
            subtitle_lang=subtitle_lang,
            subtitle_max_chars=subtitle_max_chars,
        )
    else:
        subtitles = SubtitleResponse(
            enabled=False,
            mode="disabled",
            requested_language=subtitle_lang if isinstance(subtitle_lang, str) else DEFAULT_SUBTITLE_LANG,
            available_languages=[],
            selected_language=None,
            fallback_reason=None,
            truncated=False,
            returned_chars=0,
            dropped_tracks=0,
            track_count=0,
            tracks=[],
            full_text="",
            errors=[],
        )

    payload = VideoDetailResponse(video=video_item, subtitles=subtitles)
    return payload.model_dump()


def _filter_article_stats(raw_stats: Any) -> ArticleStatsResponse:
    if not isinstance(raw_stats, dict):
        return ArticleStatsResponse()

    return ArticleStatsResponse(
        view=_coerce_int(raw_stats.get("view")),
        like=_coerce_int(raw_stats.get("like")),
        reply=_coerce_int(raw_stats.get("reply")),
        coin=_coerce_int(raw_stats.get("coin")),
        share=_coerce_int(raw_stats.get("share")),
    )


def _build_article_fallback_markdown(
    article_id: int,
    article_info: dict[str, Any] | None,
    reason: str,
) -> str:
    title = article_info.get("title") if isinstance(article_info, dict) else None
    heading = f"# {title}" if isinstance(title, str) and title.strip() else f"# cv{article_id}"

    lines = [
        heading,
        "",
        "> Full markdown content is unavailable from the current upstream payload.",
        f"> Reason: {reason}",
    ]

    if isinstance(article_info, dict):
        video_url = article_info.get("video_url")
        if isinstance(video_url, str) and video_url.strip():
            lines.extend(["", f"Source: {video_url.strip()}"])

    return "\n".join(lines)


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_user_articles(
    user_id: int,
    page: int,
    limit: int,
    cred: Credential,
) -> dict[str, Any]:
    u = user.User(uid=user_id, credential=cred)
    articles_data = await _timed_await(u.get_articles(pn=page, ps=limit))

    article_items = []
    for article_data in (articles_data.get("articles") or []):
        if len(article_items) >= limit:
            break

        article_items.append(
            ArticleListItem(
                id=_coerce_int(article_data.get("id")),
                title=article_data.get("title"),
                summary=article_data.get("summary"),
                publish_time_str=format_timestamp(_coerce_int(article_data.get("publish_time"))),
                stats=_filter_article_stats(article_data.get("stats")),
            )
        )

    payload = ArticlesResponse(
        articles=article_items,
        total=_coerce_int(articles_data.get("count"))
        or _coerce_int(articles_data.get("total"))
        or len(article_items),
    )
    return payload.model_dump()


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_article_content(
    article_id: int,
    cred: Credential | None,
) -> dict[str, Any]:
    article_client = article.Article(cvid=article_id, credential=cred)

    article_info = await _timed_await(article_client.get_info())

    try:
        # bilibili_api requires parsing content first before markdown conversion.
        await _timed_await(article_client.fetch_content())
        markdown_content = article_client.markdown()
    except KeyError as exc:
        # Some legacy CVs return a payload shape without readInfo in bilibili_api.
        logger.warning(
            "Article %s markdown payload is unsupported by upstream schema: %s",
            article_id,
            exc,
        )
        markdown_content = _build_article_fallback_markdown(
            article_id=article_id,
            article_info=article_info if isinstance(article_info, dict) else None,
            reason=f"unsupported payload key: {exc}",
        )
    except ApiException as exc:
        # Keep compatibility when upstream parser state cannot be built.
        if "fetch_content" in str(exc):
            logger.warning(
                "Article %s markdown parsing failed after fetch_content: %s",
                article_id,
                exc,
            )
            markdown_content = _build_article_fallback_markdown(
                article_id=article_id,
                article_info=article_info if isinstance(article_info, dict) else None,
                reason=str(exc),
            )
        else:
            raise

    payload = ArticleContentResponse(
        id=article_id,
        title=article_info.get("title") if isinstance(article_info, dict) else None,
        markdown_content=markdown_content if isinstance(markdown_content, str) else str(markdown_content),
    )
    return payload.model_dump()


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_user_followings(
    user_id: int,
    page: int,
    limit: int,
    cred: Credential,
) -> dict[str, Any]:
    api_url = "https://api.bilibili.com/x/relation/followings"
    params = {"vmid": user_id, "ps": limit, "pn": page}
    headers = DEFAULT_HEADERS.copy()

    cookie = _build_cookie_header(cred)
    if cookie:
        headers["Cookie"] = cookie

    started = time.perf_counter()
    response = await get_shared_http_client().get(
        api_url,
        params=params,
        headers=headers,
    )
    add_upstream_duration_ms((time.perf_counter() - started) * 1000)

    response.raise_for_status()
    payload = response.json()

    error_code = payload.get("code")
    if error_code == -509:
        raise RetryableBiliApiError(
            code=-509,
            message="Request is rate-limited by Bilibili",
        )
    if error_code in {2207, 22115}:
        raise ValueError("User followings are private")
    if error_code == -404:
        raise ValueError(f"User {user_id} does not exist")
    if error_code == -412:
        raise RetryableBiliApiError(
            code=-412,
            message="Request blocked by Bilibili",
        )
    if error_code != 0:
        raise ValueError(
            f"Bilibili API error (code: {error_code}): {payload.get('message', 'unknown error')}"
        )

    data = payload.get("data") or {}
    raw_followings = data.get("list") or []

    followings = [
        FollowingItemResponse(
            mid=item.get("mid"),
            uname=item.get("uname"),
            sign=item.get("sign"),
        )
        for item in raw_followings
    ]

    result = FollowingsResponse(followings=followings, total=data.get("total", 0))
    return result.model_dump()
