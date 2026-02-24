import asyncio
import logging
import time
from typing import Any

from async_lru import alru_cache
from bilibili_api import Credential, aid2bvid, search, user, video
from bilibili_api.exceptions import ApiException

from ..config import DEFAULT_HEADERS
from ..infra.http_client import get_shared_http_client
from ..models import (
    ArticlesResponse,
    FollowingsResponse,
    FollowingItemResponse,
    SubtitleSummary,
    UserInfoResponse,
    VideoItemResponse,
    VideoUpdatesResponse,
)
from ..observability import add_upstream_duration_ms, record_cache_hit
from ..parsers.dynamic_parser import format_timestamp
from ..retry import with_retry

logger = logging.getLogger(__name__)
SUBTITLE_CONCURRENCY = 5


async def _timed_await(awaitable: Any) -> Any:
    started = time.perf_counter()
    result = await awaitable
    add_upstream_duration_ms((time.perf_counter() - started) * 1000)
    return result


def _safe_aid_to_bvid(aid: Any) -> str | None:
    if not aid:
        return None
    try:
        return aid2bvid(aid)
    except Exception:
        return None


def _cache_hit(before: Any, after: Any) -> bool:
    return (after.hits > before.hits) if before and after else False


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
        headers["Cookie"] = "; ".join(
            f"{k}={v}" for k, v in cred.get_cookies().items() if v
        )

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


async def _get_video_subtitle_info(bvid: str, cred: Credential) -> dict[str, Any]:
    if not bvid:
        return {
            "has_subtitle": False,
            "subtitle_count": 0,
            "subtitle_list": [],
            "subtitle_summary": "No subtitles",
        }

    result = {
        "has_subtitle": False,
        "subtitle_count": 0,
        "subtitle_list": [],
        "subtitle_summary": "No subtitles",
    }

    try:
        v = video.Video(bvid=bvid, credential=cred)

        pages = []
        cid = None
        try:
            pages = await _timed_await(v.get_pages())
            if pages:
                cid = pages[0].get("cid")
        except Exception as exc:
            logger.debug("get_pages failed for %s: %s", bvid, exc)

        subtitles_data: list[dict[str, Any]] = []

        if cid:
            try:
                player_info = await _timed_await(v.get_player_info(cid=cid))
                subtitles_data = player_info.get("subtitle", {}).get("subtitles", []) or []
            except Exception as exc:
                logger.debug("get_player_info failed for %s: %s", bvid, exc)

        if not subtitles_data:
            try:
                video_info = await _timed_await(v.get_info())
                subtitles_data = video_info.get("subtitle", {}).get("list", []) or []
            except Exception as exc:
                logger.debug("get_info failed for %s: %s", bvid, exc)

        if not subtitles_data and cid:
            try:
                subtitle_response = await _timed_await(v.get_subtitle(cid=cid))
                subtitles_data = subtitle_response.get("subtitles", []) or []
            except Exception as exc:
                logger.debug("get_subtitle failed for %s: %s", bvid, exc)

        if not subtitles_data:
            return result

        result["has_subtitle"] = True
        result["subtitle_count"] = len(subtitles_data)

        languages: list[str] = []
        for sub in subtitles_data:
            if not isinstance(sub, dict):
                continue

            lan_code = sub.get("lan", "")
            is_ai_generated = (
                lan_code.startswith("ai-")
                or sub.get("ai_type", 0) > 0
                or sub.get("ai_status", 0) > 0
            )

            result["subtitle_list"].append(
                {
                    "id": sub.get("id"),
                    "lan": lan_code,
                    "lan_doc": sub.get("lan_doc"),
                    "author_mid": (sub.get("author") or {}).get("mid"),
                    "author_name": (sub.get("author") or {}).get("name"),
                    "subtitle_url": sub.get("subtitle_url"),
                    "is_ai_generated": is_ai_generated,
                }
            )

            language = sub.get("lan_doc") or sub.get("lan") or "Unknown"
            if is_ai_generated:
                language = f"{language} (AI)"
            languages.append(language)

        if languages:
            result["subtitle_summary"] = f"{len(languages)} track(s): " + ", ".join(
                languages
            )

        return result
    except Exception as exc:
        logger.warning("Failed to get subtitle info for %s: %s", bvid, exc)
        return {
            "has_subtitle": False,
            "subtitle_count": 0,
            "subtitle_list": [],
            "subtitle_summary": "Failed to fetch subtitles",
            "error": str(exc),
        }


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

    semaphore = asyncio.Semaphore(SUBTITLE_CONCURRENCY)

    async def _build_video_item(v_data: dict[str, Any]) -> VideoItemResponse:
        bvid = v_data.get("bvid") or _safe_aid_to_bvid(v_data.get("aid"))

        if bvid:
            async with semaphore:
                subtitle_info = await _get_video_subtitle_info(bvid, cred)
        else:
            subtitle_info = {
                "has_subtitle": False,
                "subtitle_count": 0,
                "subtitle_list": [],
                "subtitle_summary": "No bvid available",
            }

        return VideoItemResponse(
            bvid=bvid,
            title=v_data.get("title"),
            pic=v_data.get("pic"),
            description=v_data.get("description"),
            created=v_data.get("created"),
            created_time=format_timestamp(v_data.get("created")),
            play=v_data.get("play"),
            like=v_data.get("like"),
            subtitle=SubtitleSummary(
                has_subtitle=subtitle_info.get("has_subtitle", False),
                subtitle_summary=subtitle_info.get("subtitle_summary", "No subtitles"),
            ),
        )

    videos = await asyncio.gather(*[_build_video_item(v_data) for v_data in raw_videos])

    payload = VideoUpdatesResponse(
        videos=videos,
        total=(video_list.get("page") or {}).get("count", 0),
    )
    return payload.model_dump()


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_user_articles(
    user_id: int,
    page: int,
    limit: int,
    cred: Credential,
) -> dict[str, Any]:
    u = user.User(uid=user_id, credential=cred)
    articles_data = await _timed_await(u.get_articles(pn=page, ps=limit))

    articles = []
    for article_data in (articles_data.get("articles") or []):
        if len(articles) >= limit:
            break
        articles.append(
            {
                "id": article_data.get("id"),
                "title": article_data.get("title"),
                "summary": article_data.get("summary"),
                "publish_time": article_data.get("publish_time"),
                "publish_time_str": format_timestamp(article_data.get("publish_time")),
                "stats": article_data.get("stats"),
            }
        )

    payload = ArticlesResponse(articles=articles)
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
    headers["Cookie"] = "; ".join(
        f"{k}={v}" for k, v in cred.get_cookies().items() if v
    )

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
        raise ValueError("Request is rate-limited by Bilibili (-509)")
    if error_code in {2207, 22115}:
        raise ValueError("User followings are private")
    if error_code == -404:
        raise ValueError(f"User {user_id} does not exist")
    if error_code == -412:
        raise ApiException({"code": -412, "message": "Request blocked"})
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
