import logging
import json
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

def _parse_dynamic_card(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """解析单个动态卡片数据"""
    try:
        desc = card.get("desc", {})
        card_data_value = card.get("card")

        # 检查card数据是否已经是dict格式（新API格式）
        if isinstance(card_data_value, dict):
            card_data = card_data_value
        # 否则尝试作为JSON字符串解析（旧API格式）
        elif isinstance(card_data_value, str):
            try:
                card_data = json.loads(card_data_value)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse card data as JSON: {card_data_value[:200]}...")
                return None
        else:
            logger.warning(f"Unexpected card data type: {type(card_data_value)}, value: {card_data_value}")
            card_data = {}


        dynamic_id = desc.get("dynamic_id_str")
        timestamp = desc.get("timestamp")
        dynamic_type = desc.get("type")

        text_content = ""
        pictures = []
        video_info = None
        article_info = None
        repost_info = None

        # 类型判断: 转发
        if dynamic_type in [1, "DYNAMIC_TYPE_WORD", "DYNAMIC_TYPE_FORWARD"]:

            # 尝试在modules中获取文本内容（新API格式）
            modules = card_data.get("modules", {})
            module_dynamic = modules.get("module_dynamic", {})
            dynamic_desc = module_dynamic.get("desc", {})
            text_content = dynamic_desc.get("text", "")

            # 如果modules中没有找到，回退到旧格式
            if not text_content:
                item = card_data.get("item", {})
                text_content = item.get("content", "")

            origin_str = card_data.get("origin", "{}")
            try:
                origin_data = json.loads(origin_str)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse origin data: {origin_str[:200]}...")
                origin_data = {}

            origin_user = origin_data.get("user", {})
            origin_item = origin_data.get("item", {})
            repost_info = {
                "author": origin_user.get("name"),
                "text": origin_item.get("description") or origin_item.get("content", "")
            }

            # 类型判断: 图文动态
        elif dynamic_type in [2, "DYNAMIC_TYPE_DRAW"]:
            # 优先尝试新API格式：modules结构
            modules = card_data.get("modules", {})
            module_dynamic = modules.get("module_dynamic", {})
            dynamic_desc = module_dynamic.get("desc", {})
            text_content = dynamic_desc.get("text", "")

            # 获取图片（新格式） - 移到后面，与文本获取分开
            pictures = []

            # 如果modules中没有找到文本，回退到旧格式
            if not text_content:
                item = card_data.get("item", {})
                text_content = item.get("description", "")
                if not text_content:
                    # 尝试其他可能的字段
                    text_content = item.get("content", "")
                    if not text_content:
                        # 尝试在dynamic_render字段
                        dynamic_render = card_data.get("dynamic_render", {})
                        if dynamic_render:
                            text_content = dynamic_render.get("text", "")

            # 获取图片（新格式）- 现在在文本后处理
            if "major" in module_dynamic:
                major_info = module_dynamic.get("major", {})
                if "draw" in major_info:
                    draw_info = major_info.get("draw", {})
                    pictures = [item.get("src") for item in draw_info.get("items", []) if item.get("src")]

            # 获取图片（旧格式）- 作为最后回退
            if not pictures and "item" in card_data:
                item = card_data.get("item", {})
                pictures = [pic.get("img_src") for pic in item.get("pictures", [])]

            # 检查是否有其他可能的文本位置
            if not text_content and modules:
                # 1. 优先检查major.draw.rich_text（根据bilibili-API-collect文档）
                major = module_dynamic.get("major", {})
                if major.get("type") == "MAJOR_TYPE_DRAW":
                    draw_data = major.get("draw", {})
                    rich_text = draw_data.get("rich_text", "")
                    if rich_text:
                        text_content = rich_text

                    # 2. 检查rich_desc字段（继续原有逻辑）
                    if not text_content and "rich_desc" in module_dynamic.get("desc", {}):
                        rich_text = module_dynamic["desc"].get("rich_desc", {}).get("text", "")
                        if rich_text:
                            text_content = rich_text

                    # 3. 检查major字段中的archive title
                    if not text_content and "major" in module_dynamic:
                        major = module_dynamic["major"]
                        if "archive" in major:
                            title = major["archive"].get("title", "")
                            if title:
                                text_content = title

                    # 4. 尝试从major.draw.items中提取文本
                    if not text_content and "major" in module_dynamic:
                        major = module_dynamic["major"]
                        if major.get("type") == "MAJOR_TYPE_DRAW":
                            draw_data = major.get("draw", {})
                            items = draw_data.get("items", [])
                            for item in items:
                                item_text = item.get("text", "") or item.get("description", "")
                                if item_text:
                                    text_content = item_text
                                    break

        # 类型判断: 纯文字动态
        elif dynamic_type == 4:
            # 优先尝试新API格式：modules结构
            modules = card_data.get("modules", {})
            module_dynamic = modules.get("module_dynamic", {})
            dynamic_desc = module_dynamic.get("desc", {})
            text_content = dynamic_desc.get("text", "")

            # 如果modules中没有找到，回退到旧格式
            if not text_content:
                item = card_data.get("item", {})
                text_content = item.get("content", "")

        # 类型判断: 视频动态
        elif dynamic_type == 8 or dynamic_type == "DYNAMIC_TYPE_AV":
            # 优先尝试新API格式：modules结构
            modules = card_data.get("modules", {})
            module_dynamic = modules.get("module_dynamic", {})
            dynamic_desc = module_dynamic.get("desc", {})
            text_content = dynamic_desc.get("text", "")

            # 如果modules中没有找到，回退到多种可能的旧格式字段
            if not text_content:
                text_content = card_data.get("dynamic", "")
            if not text_content:
                text_content = card_data.get("desc", "")
            if not text_content:
                text_content = card_data.get("title", "")

            video_info = {
                "bvid": card_data.get("bvid"),
                "title": card_data.get("title"),
                "cover": card_data.get("pic"),
                "duration": card_data.get("duration"),
                "url": f"https://www.bilibili.com/video/{card_data.get('bvid')}" if card_data.get('bvid') else None
            }

        # 类型判断: 文章动态
        elif dynamic_type == 64:
            # 优先尝试新API格式：modules结构
            modules = card_data.get("modules", {})
            module_dynamic = modules.get("module_dynamic", {})
            dynamic_desc = module_dynamic.get("desc", {})
            text_content = dynamic_desc.get("text", "")

            # 如果modules中没有找到，回退到旧格式
            if not text_content:
                text_content = card_data.get("summary", "")
            if not text_content:
                text_content = card_data.get("title", "")

            article_info = {
                "id": card_data.get("id"),
                "title": card_data.get("title"),
                "summary": text_content,
                "banner_url": card_data.get("banner_url"),
                "url": f"https://www.bilibili.com/read/cv{card_data.get('id')}" if card_data.get('id') else None
            }

        else:
            # 其他未处理类型
            return None

        return {
            "dynamic_id": dynamic_id,
            "timestamp": timestamp,
            "type": dynamic_type,
            "stat": {
                "forward": desc.get("repost", 0),
                "comment": desc.get("comment", 0),
                "like": desc.get("like", 0)
            },
            "content": {
                "text": text_content,
                "pictures": pictures,
                "video": video_info,
                "article": article_info,
                "repost": repost_info
            }
        }

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"Error parsing dynamic card: {e} - Card: {card}")
        return None

def parse_dynamics_data(dynamics_page: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    解析从 bilibili-api get_dynamics 获取的整页动态数据
    """
    parsed_dynamics = []
    cards = dynamics_page.get("cards", [])
    for card in cards:
        parsed_card = _parse_dynamic_card(card)
        if parsed_card:
            parsed_dynamics.append(parsed_card)
    return parsed_dynamics
