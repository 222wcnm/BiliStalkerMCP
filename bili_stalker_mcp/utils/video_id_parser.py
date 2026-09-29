import re
from typing import Any
from urllib.parse import urlparse

from bilibili_api import aid2bvid

from ..errors import InvalidVideoIdentifierError, ShortLinkResolutionError
from ..infra.http_client import get_shared_http_client

_BV_PATTERN = re.compile(r"(?<![a-zA-Z0-9_])BV[a-zA-Z0-9]{10}(?![a-zA-Z0-9_])")
_AV_PATTERN = re.compile(r"(?:^|/)av(\d+)(?![a-zA-Z0-9_])", re.IGNORECASE)


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
        numeric_aid = int(aid)
        return aid2bvid(numeric_aid) if numeric_aid > 0 else None
    except Exception:
        return None


def _extract_local_bvid(text: str) -> str | None:
    bv_match = _BV_PATTERN.search(text)
    if bv_match:
        return bv_match.group(0)
    av_match = _AV_PATTERN.search(text)
    if av_match:
        converted = _safe_aid_to_bvid(av_match.group(1))
        if converted and _BV_PATTERN.fullmatch(converted):
            return converted
    return None


async def extract_bvid(raw: str) -> str:
    """Extract a BVID from various input formats.

    Supported inputs (in priority order):
    - Pure BVID: ``BV1xx411c7mD``
    - URL containing BVID: ``https://www.bilibili.com/video/BV1xx411c7mD/``
    - AV number: ``av170001``
    - URL containing AV number: ``https://www.bilibili.com/video/av170001/``
    - b23.tv short link: ``https://b23.tv/AbCdEfG`` (resolved via HTTP redirect)

    Raises InvalidVideoIdentifierError or ShortLinkResolutionError on failure.
    """
    text = raw.strip()
    if _is_b23_short_url(text):
        try:
            response = await get_shared_http_client().head(
                text,
                follow_redirects=True,
            )
            response.raise_for_status()
            final_url = str(response.url)
        except Exception:
            # Keep URLs and transport exception details out of public errors/logs.
            raise ShortLinkResolutionError() from None
        if not _is_b23_short_url(final_url):
            resolved = _extract_local_bvid(final_url)
            if resolved:
                return resolved
        raise ShortLinkResolutionError()

    resolved = _extract_local_bvid(text)
    if resolved:
        return resolved
    raise InvalidVideoIdentifierError()
