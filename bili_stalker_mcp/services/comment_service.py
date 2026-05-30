import asyncio
import logging
from typing import Any

from async_lru import alru_cache
from bilibili_api import Credential

from ..config import REQUEST_DELAY
from ..infra.http_client import get_json
from ..models import (
    CommentItemResponse,
    CommentMemberResponse,
    CommentRepliesResponse,
    CommentsResponse,
)
from ..parsers.dynamic_parser import format_timestamp
from ..retry import RetryableBiliApiError, with_retry
from ..utils.converters import coerce_int

logger = logging.getLogger(__name__)

_COMMENT_TYPE_VIDEO = 1
_COMMENT_SORT_HOT = 3
_COMMENT_SORT_TIME = 2


@alru_cache(maxsize=256, ttl=300)
async def _get_aid_cached(bvid: str, cred: Credential | None) -> int:
    url = "https://api.bilibili.com/x/web-interface/view"
    data = await get_json(url, params={"bvid": bvid}, cred=cred)
    if data.get("code") != 0:
        raise ValueError(f"Failed to resolve bvid {bvid}: {data.get('message')}")
    aid = coerce_int((data.get("data") or {}).get("aid"))
    if aid is None:
        raise ValueError(f"No aid returned for bvid {bvid}")
    return aid


def _parse_comment(raw: dict[str, Any]) -> CommentItemResponse:
    content_dict = raw.get("content") or {}
    member_dict = raw.get("member") or {}
    raw_replies = raw.get("replies") or []
    return CommentItemResponse(
        rpid=coerce_int(raw.get("rpid")),
        content=content_dict.get("message"),
        member=CommentMemberResponse(
            mid=coerce_int(member_dict.get("mid")),
            uname=member_dict.get("uname"),
        ),
        like=coerce_int(raw.get("like")),
        reply_count=coerce_int(raw.get("rcount")),
        publish_time=format_timestamp(coerce_int(raw.get("ctime"))),
        replies=[_parse_comment(r) for r in raw_replies if isinstance(r, dict)],
    )


def _check_comment_api_error(data: dict[str, Any], url: str) -> None:
    code = data.get("code")
    if code == -412:
        raise RetryableBiliApiError(code=-412, message=f"Request blocked by Bilibili ({url})")
    if code == -509:
        raise RetryableBiliApiError(code=-509, message=f"Request rate-limited by Bilibili ({url})")
    if code != 0:
        raise ValueError(f"Comment API error (code {code}): {data.get('message')} ({url})")


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_video_comments(
    bvid: str,
    page: int,
    limit: int,
    sort: str,
    cred: Credential | None,
) -> dict[str, Any]:
    if page > 1:
        await asyncio.sleep(REQUEST_DELAY)

    aid = await _get_aid_cached(bvid, cred)
    mode = _COMMENT_SORT_HOT if sort == "hot" else _COMMENT_SORT_TIME

    url = "https://api.bilibili.com/x/v2/reply/main"
    params: dict[str, Any] = {
        "type": _COMMENT_TYPE_VIDEO,
        "oid": aid,
        "mode": mode,
        "ps": limit,
        "pn": page,
    }
    data = await get_json(url, params=params, cred=cred)
    _check_comment_api_error(data, url)

    payload_data = data.get("data") or {}
    raw_replies = payload_data.get("replies") or []
    cursor = payload_data.get("cursor") or {}

    top_raw = (payload_data.get("top") or {}).get("upper") or (payload_data.get("top") or {}).get("admin")
    top_comment = _parse_comment(top_raw) if isinstance(top_raw, dict) else None

    comments = [_parse_comment(r) for r in raw_replies if isinstance(r, dict)]
    total = coerce_int(cursor.get("all_count")) or len(comments)

    is_end = cursor.get("is_end")
    has_more = (not is_end) if is_end is not None else (len(comments) >= limit)

    return CommentsResponse(
        comments=comments,
        top=top_comment,
        total=total,
        page=page,
        has_more=has_more,
    ).model_dump()


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_comment_replies(
    bvid: str,
    root_rpid: int,
    page: int,
    limit: int,
    cred: Credential | None,
) -> dict[str, Any]:
    if page > 1:
        await asyncio.sleep(REQUEST_DELAY)

    aid = await _get_aid_cached(bvid, cred)

    url = "https://api.bilibili.com/x/v2/reply/reply"
    params: dict[str, Any] = {
        "type": _COMMENT_TYPE_VIDEO,
        "oid": aid,
        "root": root_rpid,
        "ps": limit,
        "pn": page,
    }
    data = await get_json(url, params=params, cred=cred)
    _check_comment_api_error(data, url)

    payload_data = data.get("data") or {}
    raw_replies = payload_data.get("replies") or []
    page_info = payload_data.get("page") or {}

    replies = [_parse_comment(r) for r in raw_replies if isinstance(r, dict)]
    total = coerce_int(page_info.get("count")) or len(replies)

    return CommentRepliesResponse(
        replies=replies,
        total=total,
        page=page,
        has_more=(page * limit) < total,
    ).model_dump()
