import logging
from typing import Any, Literal

from async_lru import alru_cache
from bilibili_api import Credential, article, search, user, video
from bilibili_api.exceptions import ApiException

from ..infra.http_client import get_json
from ..infra.upstream import timed_upstream_call
from ..models import (
    ArticleContentResponse,
    ArticleListItem,
    ArticleStatsResponse,
    ArticlesResponse,
    FollowingItemResponse,
    FollowingsResponse,
    UserInfoResponse,
    VideoDetailItem,
    VideoDetailResponse,
    VideoListItem,
    VideoListResponse,
    VideoStatResponse,
)
from ..observability import record_cache_hit
from ..parsers.dynamic_parser import format_timestamp
from ..retry import RetryableBiliApiError, is_retryable_error, with_retry
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
@with_retry(max_retries=5, base_delay=2.0, return_default=True, default_on_exhaust=None)
async def _get_user_id_by_username_cached(username: str) -> int | None:
    if not username:
        return None

    search_result = await timed_upstream_call(
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
    info = await timed_upstream_call(u.get_user_info())
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
        stat_data = await get_json(
            stat_url,
            params=params,
            cred=cred,
        )

        if stat_data.get("code") == 0 and "data" in stat_data:
            user_data["following"] = stat_data["data"].get("following")
            user_data["follower"] = stat_data["data"].get("follower")
        else:
            logger.warning(
                "Failed to get relation stat for uid %s: %s",
                user_id,
                stat_data.get("message"),
            )
    except RetryableBiliApiError as exc:
        logger.warning(
            "Relation stat request was blocked or rate-limited for uid %s: %s",
            user_id,
            exc,
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

    article_items = []
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
        if is_retryable_error(exc):
            raise
        logger.warning(
            "CV %s legacy parser raised %s; falling back to opus page", cvid, exc
        )
        return info if isinstance(info, dict) else None, None, str(exc)


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
