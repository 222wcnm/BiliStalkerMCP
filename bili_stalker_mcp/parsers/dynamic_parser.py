import logging
from datetime import datetime
from typing import Any

from bilibili_api import aid2bvid

logger = logging.getLogger(__name__)


def format_timestamp(ts: int | None) -> str | None:
    if ts is None:
        return None

    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return None


def _safe_aid_to_bvid(aid: Any) -> str | None:
    if not aid:
        return None
    try:
        return aid2bvid(aid)
    except Exception:
        return None


def parse_dynamic_item(item: dict[str, Any]) -> dict[str, Any]:
    """Parse one raw dynamic card into stable output format."""
    try:
        desc = item.get("desc") or {}
        card = item.get("card")
        if card is None:
            card = {}
        if not isinstance(card, dict):
            raise TypeError("card is not a mapping")

        timestamp = desc.get("timestamp")
        parsed: dict[str, Any] = {
            "dynamic_id": desc.get("dynamic_id_str"),
            "timestamp": timestamp,
            "publish_time": format_timestamp(timestamp),
        }

        item_type_id = desc.get("type")

        if item_type_id == 1:
            parsed["type"] = "REPOST"
            parsed["text_content"] = (card.get("item") or {}).get("content")

            origin_card = card.get("origin")
            origin_desc = desc.get("origin") or {}
            origin_type = origin_desc.get("type")

            origin_user_raw = card.get("origin_user")
            origin_user = (
                (origin_user_raw or {}).get("info")
                if isinstance(origin_user_raw, dict)
                else {}
            )

            if isinstance(origin_card, dict):
                origin_info: dict[str, Any] = {
                    "user_name": origin_user.get("uname"),
                    "user_id": origin_user.get("uid"),
                }

                if origin_type == 8:
                    origin_info["type"] = "VIDEO"
                    origin_info["text_content"] = origin_card.get("dynamic")
                    origin_info["video"] = {
                        "title": origin_card.get("title"),
                        "bvid": origin_card.get("bvid")
                        or _safe_aid_to_bvid(origin_card.get("aid")),
                        "pic": origin_card.get("pic"),
                    }
                elif origin_type == 2:
                    origin_item = origin_card.get("item") or {}
                    pictures = origin_item.get("pictures") or []
                    image_urls = [
                        p.get("img_src")
                        for p in pictures
                        if isinstance(p, dict) and p.get("img_src")
                    ]
                    origin_info["type"] = "IMAGE_TEXT" if image_urls else "TEXT"
                    origin_info["text_content"] = origin_item.get("description")
                    if image_urls:
                        origin_info["images"] = image_urls
                elif origin_type == 4:
                    origin_info["type"] = "TEXT"
                    origin_info["text_content"] = (origin_card.get("item") or {}).get(
                        "content"
                    )
                elif origin_type == 64:
                    origin_info["type"] = "ARTICLE"
                    origin_info["text_content"] = origin_card.get("summary")
                    origin_info["article"] = {
                        "id": origin_card.get("id"),
                        "title": origin_card.get("title"),
                    }
                else:
                    origin_info["type"] = f"OTHER_{origin_type}"
                    origin_info["text_content"] = (
                        origin_card.get("title")
                        or origin_card.get("description")
                        or origin_card.get("content")
                        or origin_card.get("summary")
                        or ((origin_card.get("vest") or {}).get("content"))
                        or "(no text content)"
                    )

                parsed["origin"] = origin_info

        elif item_type_id == 2:
            item_data = card.get("item") or {}
            parsed["text_content"] = item_data.get("description")
            pictures = item_data.get("pictures") or []
            image_urls = [
                p.get("img_src")
                for p in pictures
                if isinstance(p, dict) and p.get("img_src")
            ]
            if image_urls:
                parsed["type"] = "IMAGE_TEXT"
                parsed["images"] = image_urls
            else:
                parsed["type"] = "TEXT"

        elif item_type_id == 4:
            parsed["type"] = "TEXT"
            parsed["text_content"] = (card.get("item") or {}).get("content")

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
                "id": card.get("id"),
                "title": card.get("title"),
            }

        elif item_type_id == 2048:
            parsed["type"] = "CHARGE_QA"
            vest_content = (card.get("vest") or {}).get("content", "")
            sketch_title = (card.get("sketch") or {}).get("title", "")
            parsed["text_content"] = f"{vest_content} {sketch_title}".strip()
            parsed["charge_info"] = {
                "vest": card.get("vest") or {},
                "sketch": card.get("sketch") or {},
            }

        elif item_type_id == 512:
            parsed["type"] = "ACTIVITY"
            parsed["text_content"] = card.get("title") or card.get("description")
            parsed["activity_info"] = {
                "title": card.get("title"),
                "description": card.get("description"),
            }

        else:
            parsed["type"] = f"UNKNOWN_{item_type_id}"
            parsed["text_content"] = f"(unsupported dynamic type {item_type_id})"

        return parsed
    except Exception as exc:
        dynamic_id = (item.get("desc") or {}).get("dynamic_id_str", "unknown")
        item_type_id = (item.get("desc") or {}).get("type", "unknown")
        logger.error(
            "Failed to parse dynamic item %s (type %s): %s",
            dynamic_id,
            item_type_id,
            exc,
        )
        return {
            "error": f"Failed to parse dynamic: {exc}",
            "id": dynamic_id,
            "type_id": item_type_id,
            "error_location": f"Type {item_type_id} parsing",
            "card_keys": list((item.get("card") or {}).keys())
            if isinstance(item.get("card"), dict)
            else [],
            "desc_keys": list((item.get("desc") or {}).keys())
            if isinstance(item.get("desc"), dict)
            else [],
            "raw_data_sample": (str(item)[:300] + "...")
            if len(str(item)) > 300
            else str(item),
        }
