import json
import logging
from datetime import datetime, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from ..config import DEFAULT_TIMEZONE
from ..utils.converters import coerce_int as _coerce_int
from ..utils.converters import safe_aid_to_bvid as _safe_aid_to_bvid

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


def _extract_module_stats(modules: dict[str, Any]) -> dict[str, int]:
    stat = _ensure_mapping(modules.get("module_stat"))

    def count(name: str) -> int:
        return _coerce_int(_ensure_mapping(stat.get(name)).get("count")) or 0

    return {
        "like": count("like"),
        "comment": count("comment"),
        "forward": count("forward"),
    }


def _extract_dynamic_text(module_dynamic: dict[str, Any]) -> str | None:
    desc_text = _ensure_mapping(module_dynamic.get("desc")).get("text")
    if isinstance(desc_text, str) and desc_text:
        return desc_text

    major = _ensure_mapping(module_dynamic.get("major"))
    opus = _ensure_mapping(major.get("opus"))
    summary_text = _ensure_mapping(opus.get("summary")).get("text")
    if isinstance(summary_text, str) and summary_text:
        return summary_text

    for key in ("archive", "article", "common", "draw"):
        payload = _ensure_mapping(major.get(key))
        for field in ("desc", "summary", "title"):
            value = payload.get(field)
            if isinstance(value, str) and value:
                return value

    return None


def _parse_new_dynamic_item(
    item: dict[str, Any],
    *,
    include_origin: bool = True,
) -> dict[str, Any]:
    modules = _ensure_mapping(item.get("modules"))
    author = _ensure_mapping(modules.get("module_author"))
    module_dynamic = _ensure_mapping(modules.get("module_dynamic"))
    major = _ensure_mapping(module_dynamic.get("major"))
    item_type = item.get("type")
    dynamic_id = item.get("id_str")

    parsed: dict[str, Any] = {
        "dynamic_id": str(dynamic_id) if dynamic_id is not None else None,
        "publish_time": format_timestamp(_coerce_int(author.get("pub_ts"))),
        "type": None,
        "text_content": _extract_dynamic_text(module_dynamic),
        "image_count": 0,
        "stats": _extract_module_stats(modules),
        "video": None,
        "article": None,
        "origin": None,
    }

    if item_type == "DYNAMIC_TYPE_FORWARD":
        parsed["type"] = "REPOST"
        if include_origin:
            origin_item = _ensure_mapping(item.get("orig"))
            if origin_item:
                origin_parsed = _parse_new_dynamic_item(
                    origin_item,
                    include_origin=False,
                )
                origin_modules = _ensure_mapping(origin_item.get("modules"))
                origin_author = _ensure_mapping(origin_modules.get("module_author"))
                parsed["origin"] = {
                    "type": origin_parsed.get("type"),
                    "text_content": origin_parsed.get("text_content"),
                    "image_count": origin_parsed.get("image_count", 0),
                    "user_name": origin_author.get("name"),
                    "user_id": _coerce_int(origin_author.get("mid")),
                    "video": origin_parsed.get("video"),
                    "article": origin_parsed.get("article"),
                }
    elif item_type == "DYNAMIC_TYPE_DRAW":
        opus = _ensure_mapping(major.get("opus"))
        draw = _ensure_mapping(major.get("draw"))
        pictures = opus.get("pics")
        if not isinstance(pictures, list):
            pictures = draw.get("items")
        parsed["type"] = "DRAW"
        parsed["image_count"] = _extract_image_count(pictures)
    elif item_type == "DYNAMIC_TYPE_WORD":
        parsed["type"] = "TEXT"
    elif item_type == "DYNAMIC_TYPE_AV":
        archive = _ensure_mapping(major.get("archive"))
        parsed["type"] = "VIDEO"
        parsed["video"] = {
            "title": archive.get("title"),
            "bvid": archive.get("bvid") or _safe_aid_to_bvid(archive.get("aid")),
        }
    elif item_type == "DYNAMIC_TYPE_ARTICLE":
        article = _ensure_mapping(major.get("article"))
        opus = _ensure_mapping(major.get("opus"))
        article_id = (
            article.get("id")
            or article.get("id_str")
            or article.get("cvid")
            or opus.get("id")
        )
        parsed["type"] = "ARTICLE"
        parsed["article"] = {
            "id": _coerce_int(article_id),
            "title": article.get("title") or opus.get("title"),
        }
    else:
        type_suffix = str(item_type or "UNKNOWN").removeprefix("DYNAMIC_TYPE_")
        parsed["type"] = f"UNKNOWN_{type_suffix}"

    if parsed.get("origin") is None:
        parsed.pop("origin", None)

    return parsed


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
        (origin_user_raw or {}).get("info") if isinstance(origin_user_raw, dict) else {}
    )

    origin: dict[str, Any] = {
        "type": None,
        "text_content": None,
        "image_count": 0,
        "user_name": (
            origin_user.get("uname") if isinstance(origin_user, dict) else None
        ),
        "user_id": (
            _coerce_int((origin_user or {}).get("uid"))
            if isinstance(origin_user, dict)
            else None
        ),
        "video": None,
        "article": None,
    }

    if origin_type == 8:
        origin["type"] = "VIDEO"
        origin["text_content"] = origin_card.get("dynamic")
        origin["video"] = {
            "title": origin_card.get("title"),
            "bvid": origin_card.get("bvid")
            or _safe_aid_to_bvid(origin_card.get("aid")),
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
    """Parse one legacy or polymer dynamic item into the stable output format."""
    if isinstance(item.get("modules"), dict):
        return _parse_new_dynamic_item(item)

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
