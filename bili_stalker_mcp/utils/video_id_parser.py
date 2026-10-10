import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from bilibili_api import aid2bvid

from ..errors import (
    InvalidSubtitleSelectionError,
    InvalidVideoIdentifierError,
    ShortLinkResolutionError,
)
from ..infra.http_client import get_shared_http_client

_BV_PATTERN = re.compile(r"(?<![a-zA-Z0-9_])BV[a-zA-Z0-9]{10}(?![a-zA-Z0-9_])")
_AV_PATTERN = re.compile(r"(?:^|/)av(\d+)(?![a-zA-Z0-9_])", re.IGNORECASE)


@dataclass(frozen=True)
class VideoReference:
    bvid: str
    page: int | None = None


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


async def _resolve_video_input(raw: str) -> tuple[str, str]:
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
                return resolved, final_url
        raise ShortLinkResolutionError()

    resolved = _extract_local_bvid(text)
    if resolved:
        return resolved, text
    raise InvalidVideoIdentifierError()


async def extract_bvid(raw: str) -> str:
    """Extract a BVID from a BVID, AV number, video URL, or b23.tv link.

    URL query parameters remain ignored for compatibility with identifier-only
    callers. Raises InvalidVideoIdentifierError or ShortLinkResolutionError.
    """
    bvid, _ = await _resolve_video_input(raw)
    return bvid


async def extract_video_reference(raw: str) -> VideoReference:
    """Resolve a video identifier and preserve the destination URL's page."""
    bvid, text = await _resolve_video_input(raw)
    values = parse_qs(urlparse(text).query, keep_blank_values=True).get("p")
    if values is None:
        return VideoReference(bvid)

    message = "Video URL p must be a single positive integer."
    if len(values) != 1 or re.fullmatch(r"[0-9]+", values[0]) is None:
        raise InvalidSubtitleSelectionError(message)
    try:
        page = int(values[0])
    except ValueError:
        raise InvalidSubtitleSelectionError(message) from None
    if page < 1:
        raise InvalidSubtitleSelectionError(message)
    return VideoReference(bvid, page)
