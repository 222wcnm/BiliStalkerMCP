import asyncio
import logging
from typing import Any, Literal

from async_lru import alru_cache
from bilibili_api import Credential, article, search, user, video
from bilibili_api.exceptions import ApiException

from ..errors import RISK_CONTROL_CODES, extract_error_code
from ..infra.http_client import get_json
from ..infra.upstream import timed_upstream_call
from ..models import (
    ArticleContentResponse,
    ArticleListItem,
    ArticlesResponse,
    ArticleStatsResponse,
    FollowingItemResponse,
    FollowingsResponse,
    UserInfoResponse,
    UserSearchItem,
    UserSearchResponse,
    VideoDetailItem,
    VideoDetailResponse,
    VideoListItem,
    VideoListResponse,
    VideoStatResponse,
)
from ..observability import record_cache_hit
from ..parsers.dynamic_parser import format_timestamp
from ..retry import (
    DEFAULT_RETRYABLE_EXCEPTIONS,
    RetryableBiliApiError,
    is_retryable_error,
    with_retry,
)
from ..utils.converters import coerce_int, safe_aid_to_bvid
from .article_renderer import (
    build_article_fallback_markdown,
    fetch_opus_payload,
)
from .subtitle_service import (
    DEFAULT_SUBTITLE_LANG,
    DEFAULT_SUBTITLE_MAX_CHARS,
    DEFAULT_SUBTITLE_MODE,
    build_disabled_subtitles,
    collect_subtitles,
)

logger = logging.getLogger(__name__)

USER_SEARCH_LIMIT = 20
USER_SEARCH_TIMEOUT_SECONDS = 10.0

# ──────────────────── internal helpers ────────────────────


def _cache_hit(before: Any, after: Any) -> bool:
    return (after.hits > before.hits) if before and after else False


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
        coerce_int(video_data.get("review")),
        coerce_int(video_data.get("video_review")),
        coerce_int(video_data.get("comment")),
    )

    for value in candidates:
        if value is not None and value > 0:
            return value

    for value in candidates:
        if value is not None:
            return value

    return None


def _normalize_video_pages(pages_raw: Any) -> list[dict[str, Any]]:
    normalized_pages: list[dict[str, Any]] = []
    if not isinstance(pages_raw, list):
        return normalized_pages

    for page in pages_raw:
        if not isinstance(page, dict):
            continue
        normalized_pages.append(
            {
                "cid": coerce_int(page.get("cid")),
                "page": coerce_int(page.get("page")),
                "part": page.get("part"),
                "duration": coerce_int(page.get("duration")),
            }
        )

    return normalized_pages


def _filter_article_stats(raw_stats: Any) -> ArticleStatsResponse:
    if not isinstance(raw_stats, dict):
        return ArticleStatsResponse()

    return ArticleStatsResponse(
        view=coerce_int(raw_stats.get("view")),
        like=coerce_int(raw_stats.get("like")),
        reply=coerce_int(raw_stats.get("reply")),
        coin=coerce_int(raw_stats.get("coin")),
        share=coerce_int(raw_stats.get("share")),
    )


# ──────────────────── public API ────────────────────


@alru_cache(maxsize=128, ttl=3600)
@with_retry(
    max_retries=1,
    base_delay=1.0,
    retryable_exceptions=(TimeoutError, *DEFAULT_RETRYABLE_EXCEPTIONS),
)
async def _search_users_cached(keyword: str) -> list[dict[str, Any]]:
    async with asyncio.timeout(USER_SEARCH_TIMEOUT_SECONDS):
        search_result = await timed_upstream_call(
            search.search_by_type(
                keyword=keyword,
                search_type=search.SearchObjectType.USER,
                page_size=USER_SEARCH_LIMIT,
            )
        )
    result_list = search_result.get("result") or (search_result.get("data") or {}).get(
        "result"
    )

    if not isinstance(result_list, list) or not result_list:
        return []

    keyword_key = keyword.casefold()
    users: list[dict[str, Any]] = []
    for user_item in result_list:
        if not isinstance(user_item, dict):
            continue
        uid = coerce_int(user_item.get("mid"))
        name = user_item.get("uname")
        if uid is None or not isinstance(name, str) or not name:
            continue
        users.append(
            UserSearchItem(
                uid=uid,
                name=name,
                sign=user_item.get("usign"),
                avatar=user_item.get("upic"),
                follower=coerce_int(user_item.get("fans")),
                videos=coerce_int(user_item.get("videos")),
                level=coerce_int(user_item.get("level")),
                is_live=(
                    bool(user_item.get("is_live")) if "is_live" in user_item else None
                ),
                is_exact_match=name.casefold() == keyword_key,
            ).model_dump()
        )
    return users


async def search_users(keyword: str, limit: int = 10) -> dict[str, Any]:
    normalized = keyword.strip()
    if not normalized:
        raise ValueError("keyword must not be empty")
    if limit < 1 or limit > USER_SEARCH_LIMIT:
        raise ValueError(f"limit must be between 1 and {USER_SEARCH_LIMIT}")

    before = _search_users_cached.cache_info()
    users = await _search_users_cached(normalized)
    after = _search_users_cached.cache_info()
    record_cache_hit("user_search", _cache_hit(before, after))

    selected = [UserSearchItem(**item) for item in users[:limit]]
    exact_match_uid = next(
        (item["uid"] for item in users if item["is_exact_match"]),
        None,
    )
    return UserSearchResponse(
        users=selected,
        count=len(selected),
        exact_match_uid=exact_match_uid,
    ).model_dump()


async def get_user_id_by_username(username: str) -> int | None:
    # Deliberately not cached on its own: reusing _search_users_cached keeps
    # username resolution consistent with search_users results at all times.
    username = username.strip()
    if not username:
        return None

    before = _search_users_cached.cache_info()
    users = await _search_users_cached(username)
    after = _search_users_cached.cache_info()
    record_cache_hit("user_id_by_username", _cache_hit(before, after))

    for user_item in users:
        if user_item["is_exact_match"]:
            return int(user_item["uid"])

    logger.warning("No exact user match for '%s'", username)
    return None


def _clean_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_user_profile(info: dict[str, Any]) -> dict[str, Any]:
    """Extract high-value profile fields from the raw space info payload."""
    official_raw = info.get("official") or {}
    vip_raw = info.get("vip") or {}
    live_raw = info.get("live_room") or {}
    school_raw = info.get("school") or {}
    profession_raw = info.get("profession") or {}

    sex = _clean_str(info.get("sex"))
    if sex == "保密":
        sex = None

    official = None
    official_title = _clean_str(official_raw.get("title"))
    if official_title:
        official = {
            "role": coerce_int(official_raw.get("role")),
            "title": official_title,
        }

    vip = None
    if isinstance(vip_raw, dict) and vip_raw:
        vip = {
            "status": bool(coerce_int(vip_raw.get("status"))),
            "label": _clean_str((vip_raw.get("label") or {}).get("text")),
        }

    live_room = None
    if coerce_int(live_raw.get("roomStatus")):
        live_room = {
            "is_live": bool(coerce_int(live_raw.get("liveStatus"))),
            "title": _clean_str(live_raw.get("title")),
            "url": _clean_str(live_raw.get("url")),
            "watched": coerce_int((live_raw.get("watched_show") or {}).get("num")),
        }

    profession_parts = [
        _clean_str(profession_raw.get("name")),
        _clean_str(profession_raw.get("title")),
    ]
    profession = " ".join(part for part in profession_parts if part) or None

    return {
        "face": _clean_str(info.get("face")),
        "level": coerce_int(info.get("level")),
        "sex": sex,
        "birthday": _clean_str(info.get("birthday")),
        "school": _clean_str(school_raw.get("name")),
        "profession": profession,
        "official": official,
        "vip": vip,
        "is_banned": (
            bool(coerce_int(info.get("silence"))) if "silence" in info else None
        ),
        "is_senior_member": (
            bool(coerce_int(info.get("is_senior_member")))
            if "is_senior_member" in info
            else None
        ),
        "live_room": live_room,
    }


@alru_cache(maxsize=32, ttl=300)
@with_retry(max_retries=3, base_delay=2.0)
async def _fetch_user_info_cached(user_id: int, cred: Credential) -> dict[str, Any]:
    u = user.User(uid=user_id, credential=cred)

    async def _fetch_relation_stat() -> dict[str, Any] | None:
        try:
            stat_data = await get_json(
                "https://api.bilibili.com/x/relation/stat",
                params={"vmid": user_id},
                cred=cred,
            )
        except RetryableBiliApiError as exc:
            logger.warning(
                "Relation stat request was blocked or rate-limited for uid %s: %s",
                user_id,
                exc,
            )
            return None
        except Exception as exc:
            logger.warning("Relation stat request failed for uid %s: %s", user_id, exc)
            return None

        data = stat_data.get("data")
        if stat_data.get("code") == 0 and isinstance(data, dict):
            return data
        logger.warning(
            "Failed to get relation stat for uid %s: %s",
            user_id,
            stat_data.get("message"),
        )
        return None

    async def _fetch_up_stat() -> dict[str, Any] | None:
        if not getattr(cred, "bili_jct", None):
            logger.debug("Skipping up stat for uid %s: bili_jct not set", user_id)
            return None
        try:
            return await timed_upstream_call(u.get_up_stat())
        except Exception as exc:
            logger.warning("Up stat request failed for uid %s: %s", user_id, exc)
            return None

    info, relation, up_stat = await asyncio.gather(
        timed_upstream_call(u.get_user_info()),
        _fetch_relation_stat(),
        _fetch_up_stat(),
    )

    if not info or "mid" not in info:
        raise ValueError(f"Invalid response for user {user_id}")

    user_data: dict[str, Any] = {
        "mid": info.get("mid"),
        "name": info.get("name"),
        "sign": info.get("sign"),
        **_parse_user_profile(info),
        "following": None,
        "follower": None,
        "total_video_views": None,
        "total_article_views": None,
        "total_likes": None,
    }

    if relation is not None:
        user_data["following"] = coerce_int(relation.get("following"))
        user_data["follower"] = coerce_int(relation.get("follower"))

    if up_stat is not None:
        user_data["total_video_views"] = coerce_int(
            (up_stat.get("archive") or {}).get("view")
        )
        user_data["total_article_views"] = coerce_int(
            (up_stat.get("article") or {}).get("view")
        )
        user_data["total_likes"] = coerce_int(up_stat.get("likes"))

    return user_data


async def fetch_user_info(user_id: int, cred: Credential) -> dict[str, Any]:
    before = _fetch_user_info_cached.cache_info()
    user_data = await _fetch_user_info_cached(user_id, cred)
    after = _fetch_user_info_cached.cache_info()
    record_cache_hit("user_info", _cache_hit(before, after))

    payload = UserInfoResponse(**user_data)
    return payload.model_dump()


@alru_cache(maxsize=64, ttl=60)
@with_retry(max_retries=3, base_delay=2.0)
async def _fetch_user_videos_cached(
    user_id: int,
    page: int,
    limit: int,
    cred: Credential,
    keyword: str = "",
) -> dict[str, Any]:
    u = user.User(uid=user_id, credential=cred)
    video_list = await timed_upstream_call(
        u.get_videos(pn=page, ps=limit, keyword=keyword)
    )
    raw_videos = (video_list.get("list") or {}).get("vlist") or []

    videos = []
    for video_data in raw_videos:
        videos.append(
            VideoListItem(
                bvid=video_data.get("bvid") or safe_aid_to_bvid(video_data.get("aid")),
                aid=coerce_int(video_data.get("aid")),
                title=video_data.get("title"),
                description=video_data.get("description"),
                author=video_data.get("author"),
                length=video_data.get("length"),
                created_time=format_timestamp(coerce_int(video_data.get("created"))),
                play=coerce_int(video_data.get("play")),
                review=_select_video_review_count(video_data),
            )
        )

    payload = VideoListResponse(
        videos=videos,
        total=coerce_int((video_list.get("page") or {}).get("count")) or 0,
    )
    return payload.model_dump()


async def fetch_user_videos(
    user_id: int,
    page: int,
    limit: int,
    cred: Credential,
    keyword: str = "",
) -> dict[str, Any]:
    before = _fetch_user_videos_cached.cache_info()
    payload = await _fetch_user_videos_cached(
        user_id, page, limit, cred, keyword=keyword
    )
    after = _fetch_user_videos_cached.cache_info()
    record_cache_hit("user_videos", _cache_hit(before, after))
    return payload


@alru_cache(maxsize=64, ttl=180)
@with_retry(max_retries=3, base_delay=2.0)
async def _fetch_video_detail_cached(
    bvid: str,
    fetch_subtitles: bool = False,
    cred: Credential | None = None,
    *,
    subtitle_mode: Literal["minimal", "smart", "full"] = DEFAULT_SUBTITLE_MODE,
    subtitle_lang: str = DEFAULT_SUBTITLE_LANG,
    subtitle_max_chars: int = DEFAULT_SUBTITLE_MAX_CHARS,
) -> dict[str, Any]:
    v = video.Video(bvid=bvid, credential=cred)

    video_info = await timed_upstream_call(v.get_info())
    video_data = video_info if isinstance(video_info, dict) else {}
    normalized_pages = _normalize_video_pages(video_data.get("pages") or [])

    stat = video_data.get("stat")
    if not isinstance(stat, dict):
        stat = {}

    video_item = VideoDetailItem(
        bvid=video_data.get("bvid") or bvid,
        aid=coerce_int(video_data.get("aid")),
        title=video_data.get("title"),
        desc=video_data.get("desc"),
        publish_time=format_timestamp(coerce_int(video_data.get("pubdate"))),
        stat=VideoStatResponse(
            view=coerce_int(stat.get("view")),
            danmaku=coerce_int(stat.get("danmaku")),
            reply=coerce_int(stat.get("reply")),
            favorite=coerce_int(stat.get("favorite")),
            coin=coerce_int(stat.get("coin")),
            share=coerce_int(stat.get("share")),
            like=coerce_int(stat.get("like")),
        ),
        tags=_extract_tags(video_data),
        pages=normalized_pages,
    )

    if fetch_subtitles:
        subtitles = await collect_subtitles(
            v,
            normalized_pages,
            cred,
            subtitle_mode=subtitle_mode,
            subtitle_lang=subtitle_lang,
            subtitle_max_chars=subtitle_max_chars,
            video_info=video_data,
        )
    else:
        subtitles = build_disabled_subtitles(subtitle_lang)

    payload = VideoDetailResponse(video=video_item, subtitles=subtitles)
    return payload.model_dump()


async def fetch_video_detail(
    bvid: str,
    fetch_subtitles: bool = False,
    cred: Credential | None = None,
    *,
    subtitle_mode: Literal["minimal", "smart", "full"] = DEFAULT_SUBTITLE_MODE,
    subtitle_lang: str = DEFAULT_SUBTITLE_LANG,
    subtitle_max_chars: int = DEFAULT_SUBTITLE_MAX_CHARS,
) -> dict[str, Any]:
    before = _fetch_video_detail_cached.cache_info()
    payload = await _fetch_video_detail_cached(
        bvid=bvid,
        fetch_subtitles=fetch_subtitles,
        cred=cred,
        subtitle_mode=subtitle_mode,
        subtitle_lang=subtitle_lang,
        subtitle_max_chars=subtitle_max_chars,
    )
    after = _fetch_video_detail_cached.cache_info()
    record_cache_hit("video_detail", _cache_hit(before, after))
    return payload


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_user_articles(
    user_id: int,
    page: int,
    limit: int,
    cred: Credential,
) -> dict[str, Any]:
    u = user.User(uid=user_id, credential=cred)
    articles_data = await timed_upstream_call(u.get_articles(pn=page, ps=limit))

    article_items: list[ArticleListItem] = []
    for article_data in articles_data.get("articles") or []:
        if len(article_items) >= limit:
            break

        article_items.append(
            ArticleListItem(
                id=coerce_int(article_data.get("id")),
                title=article_data.get("title"),
                summary=article_data.get("summary"),
                publish_time_str=format_timestamp(
                    coerce_int(article_data.get("publish_time"))
                ),
                stats=_filter_article_stats(article_data.get("stats")),
            )
        )

    payload = ArticlesResponse(
        articles=article_items,
        total=coerce_int(articles_data.get("count"))
        or coerce_int(articles_data.get("total"))
        or len(article_items),
    )
    return payload.model_dump()


# Bilibili dynamic/opus snowflake ids are 64-bit; cv ids stay well below 2^53.
# Anything above this threshold is treated as a new-style opus id.
_OPUS_ID_THRESHOLD = 1 << 53


def _opus_page_url(numeric_id: int) -> str:
    """Resolve the opus-rendered page URL for either a cv id or an opus id."""
    if numeric_id >= _OPUS_ID_THRESHOLD:
        return f"https://www.bilibili.com/opus/{numeric_id}"
    return f"https://www.bilibili.com/read/cv{numeric_id}/?jump_opus=1"


async def _legacy_cv_markdown(
    cvid: int,
    cred: Credential | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Try bilibili_api's legacy cv parser. Returns (info, markdown, error_reason).

    Schema-mismatch failures (KeyError, or non-retryable ApiException from a
    payload the SDK can't parse) return ``markdown=None`` so the caller falls
    back to the opus page. Retryable upstream errors (rate limit, anti-bot
    block, transient network) are re-raised so ``@with_retry`` on
    ``fetch_article_content`` can handle them — otherwise transient outages
    would be silently turned into a synthetic "content unavailable" success.
    """
    client = article.Article(cvid=cvid, credential=cred)
    info = await timed_upstream_call(client.get_info())
    try:
        await timed_upstream_call(client.fetch_content())
        return info if isinstance(info, dict) else None, client.markdown(), None
    except KeyError as exc:
        logger.warning(
            "CV %s legacy parser missing key %s; falling back to opus page", cvid, exc
        )
        return (
            info if isinstance(info, dict) else None,
            None,
            f"unsupported payload key: {exc}",
        )
    except ApiException as exc:
        if extract_error_code(exc) in RISK_CONTROL_CODES or is_retryable_error(exc):
            raise
        error_reason = repr(exc)
        logger.warning(
            "CV %s legacy parser raised %s; falling back to opus page",
            cvid,
            error_reason,
        )
        return info if isinstance(info, dict) else None, None, error_reason


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_article_content(
    article_id: int | str,
    cred: Credential | None,
) -> dict[str, Any]:
    """Fetch markdown for a bilibili article. Accepts a cv id or an opus snowflake id."""
    try:
        numeric_id = int(article_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"article_id must be numeric, got: {article_id!r}") from exc

    article_info: dict[str, Any] | None = None
    title: str | None = None
    markdown: str | None = None
    error_reason: str | None = None

    if numeric_id < _OPUS_ID_THRESHOLD:
        article_info, markdown, error_reason = await _legacy_cv_markdown(
            numeric_id, cred
        )
        if isinstance(article_info, dict) and isinstance(
            article_info.get("title"), str
        ):
            title = article_info["title"]

    if not (isinstance(markdown, str) and markdown.strip()):
        payload = await fetch_opus_payload(
            url=_opus_page_url(numeric_id),
            cred=cred,
            preferred_title=title,
        )
        if payload:
            title = title or (
                payload.get("title") if isinstance(payload.get("title"), str) else None
            )
            candidate = payload.get("markdown_content")
            if isinstance(candidate, str) and candidate.strip():
                markdown = candidate

    if not (isinstance(markdown, str) and markdown.strip()):
        markdown = build_article_fallback_markdown(
            article_id=numeric_id,
            article_info=article_info or ({"title": title} if title else None),
            reason=error_reason or "upstream payload unavailable",
        )

    return ArticleContentResponse(
        id=str(numeric_id),
        title=title,
        markdown_content=markdown,
    ).model_dump()


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_user_followings(
    user_id: int,
    page: int,
    limit: int,
    cred: Credential,
) -> dict[str, Any]:
    api_url = "https://api.bilibili.com/x/relation/followings"
    params = {"vmid": user_id, "ps": limit, "pn": page}
    payload = await get_json(
        api_url,
        params=params,
        cred=cred,
    )

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
