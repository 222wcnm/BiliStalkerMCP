import base64
import json
import time
from typing import Any

from bilibili_api import Credential, user

from ..config import DynamicType
from ..models import DynamicUpdatesResponse
from ..observability import add_upstream_duration_ms
from ..parsers.dynamic_parser import parse_dynamic_item
from ..retry import with_retry

CURSOR_VERSION = 1
FIRST_PAGE_CURSOR = 0


def normalize_dynamic_type(dynamic_type: str) -> str:
    normalized = (dynamic_type or "").strip().upper()
    if normalized not in DynamicType.VALID_TYPES:
        allowed_values = ", ".join(DynamicType.VALID_TYPES)
        raise ValueError(
            f"Invalid dynamic_type '{dynamic_type}'. Allowed values: {allowed_values}."
        )
    return normalized


def is_dynamic_type_match(item_type_id: Any, dynamic_type: str) -> bool:
    if dynamic_type == DynamicType.ALL:
        return item_type_id in {1, 2, 4}
    if dynamic_type == DynamicType.ALL_RAW:
        return True
    if dynamic_type == DynamicType.VIDEO:
        return item_type_id == 8
    if dynamic_type == DynamicType.ARTICLE:
        return item_type_id == 64
    if dynamic_type == DynamicType.DRAW:
        return item_type_id == 2
    if dynamic_type == DynamicType.TEXT:
        return item_type_id == 4
    return False


def encode_cursor_token(
    *,
    api_cursor: Any,
    skip_matches: int,
    user_id: int,
    dynamic_type: str,
) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "u": user_id,
        "t": dynamic_type,
        "a": api_cursor,
        "s": skip_matches,
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor_token(
    cursor: str,
    *,
    user_id: int,
    dynamic_type: str,
) -> tuple[Any, int]:
    if not cursor:
        raise ValueError("cursor cannot be empty")

    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid cursor format") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid cursor payload")
    if payload.get("v") != CURSOR_VERSION:
        raise ValueError("Unsupported cursor version")
    if payload.get("u") != user_id:
        raise ValueError("Cursor does not belong to this user")
    if payload.get("t") != dynamic_type:
        raise ValueError("Cursor does not match dynamic_type")

    skip_matches = payload.get("s", 0)
    if not isinstance(skip_matches, int) or skip_matches < 0:
        raise ValueError("Invalid cursor skip value")

    api_cursor = payload.get("a", FIRST_PAGE_CURSOR)
    if api_cursor is None:
        api_cursor = FIRST_PAGE_CURSOR
    return api_cursor, skip_matches


@with_retry(max_retries=3, base_delay=2.0)
async def fetch_user_dynamics(
    user_id: int,
    offset: int,
    limit: int,
    cred: Credential,
    dynamic_type: str = "ALL",
    cursor: str | None = None,
) -> dict[str, Any]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if cursor and offset > 0:
        raise ValueError("offset is deprecated and cannot be combined with cursor")

    dynamic_type = normalize_dynamic_type(dynamic_type)

    u = user.User(uid=user_id, credential=cred)
    processed_dynamics: list[dict[str, Any]] = []

    if cursor:
        current_cursor, in_page_skip = decode_cursor_token(
            cursor,
            user_id=user_id,
            dynamic_type=dynamic_type,
        )
        legacy_skip_remaining = 0
    else:
        current_cursor = FIRST_PAGE_CURSOR
        in_page_skip = 0
        legacy_skip_remaining = offset

    next_cursor: str | None = None
    has_more = False

    while len(processed_dynamics) < limit:
        call_started = time.perf_counter()
        raw_dynamics_data = await u.get_dynamics(offset=current_cursor)
        add_upstream_duration_ms((time.perf_counter() - call_started) * 1000)

        cards = (raw_dynamics_data or {}).get("cards") or []
        page_next_offset = (raw_dynamics_data or {}).get("next_offset")
        page_has_more = bool((raw_dynamics_data or {}).get("has_more") and page_next_offset)

        if not cards:
            next_cursor = None
            has_more = False
            break

        matched_count_in_page = 0
        page_limit_reached = False
        remaining_match_in_page = False

        for index, card in enumerate(cards):
            item_type_id = (card.get("desc") or {}).get("type")
            if not is_dynamic_type_match(item_type_id, dynamic_type):
                continue

            matched_count_in_page += 1

            if matched_count_in_page <= in_page_skip:
                continue

            if legacy_skip_remaining > 0:
                legacy_skip_remaining -= 1
                continue

            processed_dynamics.append(parse_dynamic_item(card))
            if len(processed_dynamics) >= limit:
                remaining_match_in_page = any(
                    is_dynamic_type_match(
                        (tail.get("desc") or {}).get("type"),
                        dynamic_type,
                    )
                    for tail in cards[index + 1 :]
                )
                page_limit_reached = True
                break

        if page_limit_reached:
            if remaining_match_in_page:
                next_cursor = encode_cursor_token(
                    api_cursor=current_cursor,
                    skip_matches=matched_count_in_page,
                    user_id=user_id,
                    dynamic_type=dynamic_type,
                )
                has_more = True
            elif page_has_more:
                next_cursor = encode_cursor_token(
                    api_cursor=page_next_offset,
                    skip_matches=0,
                    user_id=user_id,
                    dynamic_type=dynamic_type,
                )
                has_more = True
            else:
                next_cursor = None
                has_more = False
            break

        if page_has_more:
            current_cursor = page_next_offset
            in_page_skip = 0
            next_cursor = encode_cursor_token(
                api_cursor=current_cursor,
                skip_matches=0,
                user_id=user_id,
                dynamic_type=dynamic_type,
            )
            has_more = True
            continue

        next_cursor = None
        has_more = False
        break

    payload = DynamicUpdatesResponse(
        dynamics=processed_dynamics,
        total_fetched=len(processed_dynamics),
        filter_type=dynamic_type,
        next_cursor=next_cursor,
        has_more=has_more,
    )
    return payload.model_dump()
