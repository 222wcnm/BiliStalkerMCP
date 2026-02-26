import json
import logging
from datetime import datetime, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from bilibili_api import aid2bvid

from ..config import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)
_OUTPUT_TZ: tzinfo
try:
    _OUTPUT_TZ = ZoneInfo(DEFAULT_TIMEZONE)
except Exception:
    logger.warning("Invalid BILI_TIMEZONE '%s', falling back to UTC", DEFAULT_TIMEZONE)
    _OUTPUT_TZ = timezone.utc


def format_timestamp(ts: int | None) -> str | None:
    if ts is None:
        return None

    try:
        return datetime.fromtimestamp(ts, tz=_OUTPUT_TZ).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return None


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


def _ensure_mapping(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}

    return {}


def _extract_stats(desc: dict[str, Any]) -> dict[str, int]:
    forward = _coerce_int(desc.get("repost"))
    if forward is None:
        forward = _coerce_int(desc.get("forward"))

    return {
        "like": _coerce_int(desc.get("like")) or 0,
        "comment": _coerce_int(desc.get("comment")) or 0,
        "forward": forward if forward is not None else 0,
    }


def _extract_image_count(raw_pictures: Any) -> int:
    if not isinstance(raw_pictures, list):
        return 0
    return sum(1 for picture in raw_pictures if isinstance(picture, dict))


def _parse_origin(desc: dict[str, Any], card: dict[str, Any]) -> dict[str, Any] | None:
    origin_card = _ensure_mapping(card.get("origin"))
    if not origin_card:
        return None

    origin_desc = desc.get("origin")
    if not isinstance(origin_desc, dict):
        origin_desc = {}

    origin_type = origin_desc.get("type")
    origin_user_raw = card.get("origin_user")
    origin_user = (
        (origin_user_raw or {}).get("info")
        if isinstance(origin_user_raw, dict)
        else {}
    )

    origin: dict[str, Any] = {
        "type": None,
        "text_content": None,
        "image_count": 0,
        "user_name": origin_user.get("uname") if isinstance(origin_user, dict) else None,
        "user_id": _coerce_int((origin_user or {}).get("uid")) if isinstance(origin_user, dict) else None,
        "video": None,
        "article": None,
    }

    if origin_type == 8:
        origin["type"] = "VIDEO"
        origin["text_content"] = origin_card.get("dynamic")
        origin["video"] = {
            "title": origin_card.get("title"),
            "bvid": origin_card.get("bvid") or _safe_aid_to_bvid(origin_card.get("aid")),
        }
    elif origin_type == 2:
        origin_item = origin_card.get("item")
        if not isinstance(origin_item, dict):
            origin_item = {}

        image_count = _extract_image_count(origin_item.get("pictures"))
        origin["type"] = "DRAW" if image_count > 0 else "TEXT"
        origin["text_content"] = origin_item.get("description")
        origin["image_count"] = image_count
    elif origin_type == 4:
        origin["type"] = "TEXT"
        origin_item = origin_card.get("item")
        if not isinstance(origin_item, dict):
            origin_item = {}
        origin["text_content"] = origin_item.get("content")
    elif origin_type == 64:
        origin["type"] = "ARTICLE"
        origin["text_content"] = origin_card.get("summary")
        origin["article"] = {
            "id": _coerce_int(origin_card.get("id")),
            "title": origin_card.get("title"),
        }
    else:
        origin["type"] = f"OTHER_{origin_type}"
        origin["text_content"] = (
            origin_card.get("title")
            or origin_card.get("description")
            or origin_card.get("content")
            or origin_card.get("summary")
            or (_ensure_mapping(origin_card.get("vest")).get("content"))
            or None
        )

    return origin


def parse_dynamic_item(item: dict[str, Any]) -> dict[str, Any]:
    """Parse one raw dynamic card into v3 stable output format."""
    desc = _ensure_mapping(item.get("desc"))
    card = _ensure_mapping(item.get("card"))
    timestamp = _coerce_int(desc.get("timestamp"))
    item_type_id = desc.get("type")

    parsed: dict[str, Any] = {
        "dynamic_id": desc.get("dynamic_id_str"),
        "publish_time": format_timestamp(timestamp),
        "type": None,
        "text_content": None,
        "image_count": 0,
        "stats": _extract_stats(desc),
        "video": None,
        "article": None,
        "origin": None,
    }

    try:
        if item_type_id == 1:
            parsed["type"] = "REPOST"
            parsed["text_content"] = _ensure_mapping(card.get("item")).get("content")
            parsed["origin"] = _parse_origin(desc, card)

        elif item_type_id == 2:
            item_data = _ensure_mapping(card.get("item"))
            image_count = _extract_image_count(item_data.get("pictures"))

            parsed["type"] = "DRAW" if image_count > 0 else "TEXT"
            parsed["text_content"] = item_data.get("description")
            parsed["image_count"] = image_count

        elif item_type_id == 4:
            parsed["type"] = "TEXT"
            parsed["text_content"] = _ensure_mapping(card.get("item")).get("content")

        elif item_type_id == 8:
            parsed["type"] = "VIDEO"
            parsed["text_content"] = card.get("dynamic")
            parsed["video"] = {
                "title": card.get("title"),
                "bvid": card.get("bvid") or _safe_aid_to_bvid(card.get("aid")),
            }

        elif item_type_id == 64:
            parsed["type"] = "ARTICLE"
            parsed["text_content"] = card.get("summary")
            parsed["article"] = {
                "id": _coerce_int(card.get("id")),
                "title": card.get("title"),
            }

        elif item_type_id == 2048:
            parsed["type"] = "CHARGE_QA"
            vest_content = _ensure_mapping(card.get("vest")).get("content") or ""
            sketch_title = _ensure_mapping(card.get("sketch")).get("title") or ""
            parsed["text_content"] = f"{vest_content} {sketch_title}".strip() or None

        elif item_type_id == 512:
            parsed["type"] = "ACTIVITY"
            parsed["text_content"] = card.get("title") or card.get("description")

        else:
            parsed["type"] = f"UNKNOWN_{item_type_id}"
            parsed["text_content"] = f"(unsupported dynamic type {item_type_id})"

        if parsed.get("origin") is None:
            parsed.pop("origin", None)

        return parsed
    except Exception as exc:
        dynamic_id = desc.get("dynamic_id_str", "unknown")
        logger.error(
            "Failed to parse dynamic item %s (type %s): %s",
            dynamic_id,
            item_type_id,
            exc,
        )
        parsed["type"] = "PARSE_ERROR"
        parsed["text_content"] = f"Failed to parse dynamic item: {exc}"
        return parsed
