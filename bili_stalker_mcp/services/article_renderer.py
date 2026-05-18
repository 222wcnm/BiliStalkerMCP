"""Markdown rendering for Bilibili article (opus/read) content."""

import logging
from typing import Any

from bilibili_api import Credential
from bilibili_api.utils.initial_state import get_initial_state

from ..infra.upstream import timed_upstream_call
from ..utils.converters import coerce_int

logger = logging.getLogger(__name__)


def _normalize_http_url(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    value = url.strip()
    if not value:
        return None
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value.lstrip('/')}"


def _render_module_word_node(node: dict[str, Any]) -> str:
    word = node.get("word")
    if not isinstance(word, dict):
        return ""

    text = word.get("words")
    if not isinstance(text, str):
        return ""

    style = word.get("style")
    if not isinstance(style, dict):
        style = {}

    rendered = text
    if style.get("strikethrough"):
        rendered = f"~~{rendered}~~"
    if style.get("underline"):
        rendered = f"<u>{rendered}</u>"
    if style.get("italic"):
        rendered = f"*{rendered}*"
    if style.get("bold"):
        rendered = f"**{rendered}**"
    return rendered


def _render_module_rich_node(node: dict[str, Any]) -> str:
    rich = node.get("rich")
    if not isinstance(rich, dict):
        return ""

    label = rich.get("text")
    if not isinstance(label, str) or not label.strip():
        label = rich.get("orig_text")
    if not isinstance(label, str) or not label.strip():
        label = rich.get("jump_url")
    if not isinstance(label, str):
        label = ""
    label = label.strip()

    jump_url = _normalize_http_url(rich.get("jump_url"))
    if jump_url and label:
        return f"[{label}]({jump_url})"
    if jump_url:
        return jump_url
    return label


def _render_module_text_nodes(nodes: Any) -> str:
    if not isinstance(nodes, list):
        return ""

    fragments: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        if node_type == "TEXT_NODE_TYPE_WORD":
            fragments.append(_render_module_word_node(node))
            continue
        if node_type == "TEXT_NODE_TYPE_RICH":
            fragments.append(_render_module_rich_node(node))

    return "".join(fragments).replace("\r\n", "\n").replace("\r", "\n")


def _render_module_text_block(block: Any) -> str:
    if isinstance(block, str):
        return block.strip()
    if not isinstance(block, dict):
        return ""

    nodes = block.get("nodes")
    if isinstance(nodes, list):
        return _render_module_text_nodes(nodes).strip()

    for key in ("text", "words", "content", "title"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_title_from_initial_state(initial_state: dict[str, Any]) -> str | None:
    detail = initial_state.get("detail")
    if not isinstance(detail, dict):
        return None

    basic = detail.get("basic")
    if isinstance(basic, dict):
        basic_title = basic.get("title")
        if isinstance(basic_title, str) and basic_title.strip():
            return basic_title.strip()

    modules = detail.get("modules")
    if not isinstance(modules, list):
        return None

    for module in modules:
        if not isinstance(module, dict):
            continue
        title_block = module.get("module_title")
        if not isinstance(title_block, dict):
            continue
        module_title = title_block.get("text")
        if isinstance(module_title, str) and module_title.strip():
            return module_title.strip()
    return None


def _extract_content_paragraphs(initial_state: dict[str, Any]) -> list[dict[str, Any]]:
    detail = initial_state.get("detail")
    if not isinstance(detail, dict):
        return []

    modules = detail.get("modules")
    if not isinstance(modules, list):
        return []

    for module in modules:
        if not isinstance(module, dict):
            continue
        content_block = module.get("module_content")
        if not isinstance(content_block, dict):
            continue
        paragraphs = content_block.get("paragraphs")
        if isinstance(paragraphs, list):
            return [p for p in paragraphs if isinstance(p, dict)]
    return []


def _render_content_paragraph(paragraph: dict[str, Any], *, has_top_title: bool) -> str | None:
    para_type = coerce_int(paragraph.get("para_type"))

    if para_type == 1:
        content = _render_module_text_block(paragraph.get("text")).strip("\n").strip()
        return content or None

    if para_type == 2:
        pic_block = paragraph.get("pic")
        if not isinstance(pic_block, dict):
            return None
        pics = pic_block.get("pics")
        if not isinstance(pics, list):
            return None
        image_lines: list[str] = []
        for pic in pics:
            if not isinstance(pic, dict):
                continue
            url = _normalize_http_url(pic.get("url"))
            if not url:
                continue
            image_lines.append(f"![]({url})")
        if not image_lines:
            return None
        return "\n\n".join(image_lines)

    if para_type == 3:
        return "---"

    if para_type == 8:
        heading_block = paragraph.get("heading")
        if not isinstance(heading_block, dict):
            return None
        heading_text = _render_module_text_block(heading_block).strip()
        if not heading_text:
            return None
        heading_level = coerce_int(heading_block.get("level")) or 1
        if has_top_title and heading_level < 6:
            heading_level += 1
        heading_level = min(max(1, heading_level), 6)
        return f"{'#' * heading_level} {heading_text}"

    fallback = _render_module_text_block(paragraph.get("text")).strip()
    return fallback or None


def _build_markdown_from_initial_state(
    initial_state: dict[str, Any],
    preferred_title: str | None,
) -> str | None:
    paragraphs = _extract_content_paragraphs(initial_state)
    if not paragraphs:
        return None

    title = preferred_title.strip() if isinstance(preferred_title, str) and preferred_title.strip() else None
    if not title:
        title = _extract_title_from_initial_state(initial_state)

    sections: list[str] = []
    has_top_title = bool(title)
    if has_top_title and title is not None:
        sections.append(f"# {title}")

    for paragraph in paragraphs:
        rendered = _render_content_paragraph(paragraph, has_top_title=has_top_title)
        if not rendered:
            continue
        rendered = rendered.strip()
        if rendered:
            sections.append(rendered)

    if not sections:
        return None
    return "\n\n".join(sections).strip()


def build_article_fallback_markdown(
    article_id: int,
    article_info: dict[str, Any] | None,
    reason: str,
) -> str:
    title = article_info.get("title") if isinstance(article_info, dict) else None
    heading = f"# {title}" if isinstance(title, str) and title.strip() else f"# cv{article_id}"

    lines = [
        heading,
        "",
        "> Full markdown content is unavailable from the current upstream payload.",
        f"> Reason: {reason}",
    ]

    if isinstance(article_info, dict):
        video_url = article_info.get("video_url")
        if isinstance(video_url, str) and video_url.strip():
            lines.extend(["", f"Source: {video_url.strip()}"])

    return "\n".join(lines)


async def fetch_opus_payload(
    url: str,
    cred: Credential | None,
    preferred_title: str | None = None,
) -> dict[str, Any] | None:
    """Fetch an opus-rendered bilibili page and parse title/rid/uid/markdown.

    Works for both new-style ``bilibili.com/opus/{snowflake}`` URLs and legacy
    ``bilibili.com/read/cv{id}/?jump_opus=1`` redirects — they share the same
    ``detail.modules.paragraphs`` payload shape.
    """
    credential = cred if cred is not None else Credential()

    try:
        initial_state, _ = await timed_upstream_call(
            get_initial_state(url=url, credential=credential)
        )
    except Exception as exc:
        logger.warning("Opus payload extraction failed for %s: %s", url, exc)
        return None

    if not isinstance(initial_state, dict):
        return None

    detail = initial_state.get("detail")
    basic = detail.get("basic") if isinstance(detail, dict) else None
    basic = basic if isinstance(basic, dict) else {}

    fetched_title = basic.get("title") if isinstance(basic.get("title"), str) else None
    title = (
        preferred_title
        if isinstance(preferred_title, str) and preferred_title.strip()
        else fetched_title
    )

    rid_str = basic.get("rid_str") if isinstance(basic.get("rid_str"), str) else None
    markdown = _build_markdown_from_initial_state(initial_state, preferred_title=title)

    return {
        "title": title,
        "rid": coerce_int(rid_str) if rid_str else None,
        "uid": coerce_int(basic.get("uid")),
        "markdown_content": markdown,
    }
