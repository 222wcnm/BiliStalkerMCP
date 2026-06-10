import asyncio
import logging
from typing import Any

from bilibili_api import Credential, bvid2aid, dynamic

from ..config import REQUEST_DELAY
from ..infra.http_client import get_json
from ..infra.upstream import timed_upstream_call
from ..models import (
    CommentItemResponse,
    CommentMemberResponse,
    CommentNoteResponse,
    CommentPictureResponse,
    CommentRepliesResponse,
    CommentsResponse,
)
from ..parsers.dynamic_parser import format_timestamp
from ..retry import RetryableBiliApiError, with_retry
from ..utils.converters import coerce_int

logger = logging.getLogger(__name__)

_COMMENT_TYPE_VIDEO = 1
_COMMENT_TYPE_ARTICLE = 12
_COMMENT_SORT_HOT = 3
_COMMENT_SORT_TIME = 2
_OPUS_ID_THRESHOLD = 1 << 53
_SUPPORTED_CONTENT_TYPES = {"video", "article", "dynamic"}


def _normalize_url(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    if value.startswith("//"):
        return f"https:{value}"
    return value


def _parse_pictures(raw_pictures: Any) -> list[CommentPictureResponse]:
    if not isinstance(raw_pictures, list):
        return []

    pictures: list[CommentPictureResponse] = []
    for raw_picture in raw_pictures:
        if not isinstance(raw_picture, dict):
            continue
        url = _normalize_url(raw_picture.get("img_src"))
        if not url:
            continue
        pictures.append(
            CommentPictureResponse(
                url=url,
                width=raw_picture.get("img_width"),
                height=raw_picture.get("img_height"),
                size_kb=raw_picture.get("img_size"),
            )
        )
    return pictures


def _parse_note(
    raw: dict[str, Any],
    content_dict: dict[str, Any],
    pictures: list[CommentPictureResponse],
) -> CommentNoteResponse | None:
    reply_control = raw.get("reply_control")
    if not isinstance(reply_control, dict):
        reply_control = {}

    rich_text = content_dict.get("rich_text")
    if not isinstance(rich_text, dict):
        rich_text = {}
    rich_note = rich_text.get("note")
    if not isinstance(rich_note, dict):
        rich_note = {}

    note_cvid_raw = raw.get("note_cvid_str") or raw.get("note_cvid")
    note_cvid = str(note_cvid_raw) if note_cvid_raw not in (None, "", 0, "0") else None
    is_note = bool(
        note_cvid
        or rich_note
        or reply_control.get("is_note")
        or reply_control.get("is_note_v2")
        or reply_control.get("biz_scene") == "note"
    )
    if not is_note:
        return None

    summary = rich_note.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = content_dict.get("message")
    if not isinstance(summary, str):
        summary = None

    raw_images = rich_note.get("images")
    images = (
        [
            normalized
            for item in raw_images
            if (normalized := _normalize_url(item)) is not None
        ]
        if isinstance(raw_images, list)
        else []
    )
    if not images:
        images = [picture.url for picture in pictures]

    note_url = _normalize_url(rich_note.get("click_url"))
    if not note_url and note_cvid:
        note_url = f"https://www.bilibili.com/read/cv{note_cvid}/?jump_opus=1"

    return CommentNoteResponse(
        cvid=note_cvid,
        summary=summary,
        images=images,
        url=note_url,
        content_is_preview=True,
    )


def _parse_comment(raw: dict[str, Any]) -> CommentItemResponse:
    content_dict = raw.get("content") or {}
    if not isinstance(content_dict, dict):
        content_dict = {}
    member_dict = raw.get("member") or {}
    if not isinstance(member_dict, dict):
        member_dict = {}
    raw_replies = raw.get("replies") or []
    pictures = _parse_pictures(content_dict.get("pictures"))

    return CommentItemResponse(
        rpid=coerce_int(raw.get("rpid")),
        root_rpid=coerce_int(raw.get("root")),
        parent_rpid=coerce_int(raw.get("parent")),
        content=content_dict.get("message"),
        member=CommentMemberResponse(
            mid=coerce_int(member_dict.get("mid")),
            uname=member_dict.get("uname"),
        ),
        like=coerce_int(raw.get("like")),
        reply_count=coerce_int(raw.get("rcount")),
        publish_time=format_timestamp(coerce_int(raw.get("ctime"))),
        pictures=pictures,
        note=_parse_note(raw, content_dict, pictures),
        replies=[_parse_comment(r) for r in raw_replies if isinstance(r, dict)],
    )


def _check_comment_api_error(data: dict[str, Any], url: str) -> None:
    code = data.get("code")
    if code == -412:
        raise RetryableBiliApiError(
            code=-412, message=f"Request blocked by Bilibili ({url})"
        )
    if code == -509:
        raise RetryableBiliApiError(
            code=-509, message=f"Request rate-limited by Bilibili ({url})"
        )
    if code != 0:
        raise ValueError(
            f"Comment API error (code {code}): {data.get('message')} ({url})"
        )


async def _resolve_comment_resource(
    content_type: str,
    content_id: str,
    cred: Credential | None,
) -> tuple[int, int]:
    normalized_type = content_type.strip().lower()
    if normalized_type not in _SUPPORTED_CONTENT_TYPES:
        allowed = ", ".join(sorted(_SUPPORTED_CONTENT_TYPES))
        raise ValueError(
            f"Unsupported content_type {content_type!r}. Allowed values: {allowed}."
        )

    if normalized_type == "video":
        return bvid2aid(content_id), _COMMENT_TYPE_VIDEO

    try:
        numeric_id = int(content_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{normalized_type} content_id must be a positive numeric string"
        ) from exc
    if numeric_id < 1:
        raise ValueError(f"{normalized_type} content_id must be positive")

    if normalized_type == "article" and numeric_id < _OPUS_ID_THRESHOLD:
        return numeric_id, _COMMENT_TYPE_ARTICLE

    detail = await timed_upstream_call(
        dynamic.Dynamic(dynamic_id=numeric_id, credential=cred).get_info()
    )
    item = detail.get("item") if isinstance(detail, dict) else None
    basic = item.get("basic") if isinstance(item, dict) else None
    if not isinstance(basic, dict):
        raise ValueError(f"No comment metadata returned for dynamic {numeric_id}")

    oid = coerce_int(basic.get("rid_str"))
    comment_type = coerce_int(basic.get("comment_type"))
    if oid is None or comment_type is None:
        raise ValueError(f"Incomplete comment metadata for dynamic {numeric_id}")
    return oid, comment_type


async def _fetch_comments_page(
    oid: int,
    comment_type: int,
    cursor: str | None,
    limit: int,
    sort: str,
    cred: Credential | None,
) -> dict[str, Any]:
    # reply/main is cursor-paginated: the first page omits `next`, and each
    # subsequent page must echo back the previous response's cursor. For the
    # time sort the cursor is a content-derived value (not a page index), so a
    # stateless page number cannot work — callers carry `cursor` forward.
    if cursor:
        await asyncio.sleep(REQUEST_DELAY)

    mode = _COMMENT_SORT_HOT if sort == "hot" else _COMMENT_SORT_TIME

    url = "https://api.bilibili.com/x/v2/reply/main"
    params: dict[str, Any] = {
        "type": comment_type,
        "oid": oid,
        "mode": mode,
        "ps": limit,
    }
    if cursor:
        params["next"] = cursor

    data = await get_json(url, params=params, cred=cred)
    _check_comment_api_error(data, url)

    payload_data = data.get("data") or {}
    raw_replies = payload_data.get("replies") or []
    cursor_info = payload_data.get("cursor") or {}

    # `top` is only returned on the first page; preserve it when present.
    top_raw = (payload_data.get("top") or {}).get("upper") or (
        payload_data.get("top") or {}
    ).get("admin")
    top_comment = _parse_comment(top_raw) if isinstance(top_raw, dict) else None

    comments = [_parse_comment(r) for r in raw_replies if isinstance(r, dict)]
    total = coerce_int(cursor_info.get("all_count")) or len(comments)

    is_end = cursor_info.get("is_end")
    has_more = (not is_end) if is_end is not None else (len(comments) >= limit)
    next_cursor = (
        str(cursor_info.get("next"))
        if has_more and cursor_info.get("next") is not None
        else None
    )

    return CommentsResponse(
        comments=comments,
        top=top_comment,
        count=len(comments),
        total=total,
        next_cursor=next_cursor,
        has_more=has_more,
    ).model_dump()


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_content_comments(
    content_type: str,
    content_id: str,
    cursor: str | None,
    limit: int,
    sort: str,
    cred: Credential | None,
) -> dict[str, Any]:
    oid, comment_type = await _resolve_comment_resource(content_type, content_id, cred)
    return await _fetch_comments_page(
        oid=oid,
        comment_type=comment_type,
        cursor=cursor,
        limit=limit,
        sort=sort,
        cred=cred,
    )


async def _fetch_comment_replies_page(
    oid: int,
    comment_type: int,
    root_rpid: int,
    page: int,
    limit: int,
    cred: Credential | None,
) -> dict[str, Any]:
    if page > 1:
        await asyncio.sleep(REQUEST_DELAY)

    url = "https://api.bilibili.com/x/v2/reply/reply"
    params: dict[str, Any] = {
        "type": comment_type,
        "oid": oid,
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
        count=len(replies),
        total=total,
        page=page,
        has_more=(page * limit) < total,
    ).model_dump()


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_content_comment_replies(
    content_type: str,
    content_id: str,
    root_rpid: int,
    page: int,
    limit: int,
    cred: Credential | None,
) -> dict[str, Any]:
    oid, comment_type = await _resolve_comment_resource(content_type, content_id, cred)
    return await _fetch_comment_replies_page(
        oid=oid,
        comment_type=comment_type,
        root_rpid=root_rpid,
        page=page,
        limit=limit,
        cred=cred,
    )
