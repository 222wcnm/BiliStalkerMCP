import logging
import re
from typing import Any
from urllib.parse import urlparse

from bilibili_api import aid2bvid

from ..infra.http_client import get_shared_http_client

logger = logging.getLogger(__name__)

_BV_PATTERN = re.compile(r"BV[a-zA-Z0-9_]+")
_AV_PATTERN = re.compile(r"(?:^|/)av(\d+)", re.IGNORECASE)


def _is_b23_short_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme.lower() in {"http", "https"}
        and (parsed.hostname or "").lower() == "b23.tv"
    )


def _safe_aid_to_bvid(aid: Any) -> str | None:
    if not aid:
        return None
    try:
        return aid2bvid(int(aid))
    except Exception:
        return None


async def extract_bvid(raw: str) -> str:
    """Extract a BVID from various input formats.

    Supported inputs (in priority order):
    - Pure BVID: ``BV1xx411c7mD``
    - URL containing BVID: ``https://www.bilibili.com/video/BV1xx411c7mD/``
    - AV number: ``av170001``
    - URL containing AV number: ``https://www.bilibili.com/video/av170001/``
    - b23.tv short link: ``https://b23.tv/AbCdEfG`` (resolved via HTTP redirect)

    Returns the original string unchanged when no identifier can be extracted.
    """
    text = raw.strip()
    if not text:
        return raw

    bv_match = _BV_PATTERN.search(text)
    if bv_match:
        return bv_match.group(0)

    av_match = _AV_PATTERN.search(text)
    if av_match:
        converted = _safe_aid_to_bvid(av_match.group(1))
        if converted:
            return converted

    if _is_b23_short_url(text):
        try:
            response = await get_shared_http_client().head(
                text,
                follow_redirects=True,
            )
            final_url = str(response.url)
            bv_match = _BV_PATTERN.search(final_url)
            if bv_match:
                return bv_match.group(0)
        except Exception as exc:
            logger.warning("Failed to resolve short URL %s: %s", text, exc)

    return raw
