import asyncio
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from async_lru import alru_cache
from bilibili_api import aid2bvid

from ..config import SHORT_LINK_TIMEOUT_SECONDS
from ..deadline import wait_cached, without_request_deadline
from ..errors import (
    InvalidSubtitleSelectionError,
    InvalidVideoIdentifierError,
    ShortLinkResolutionError,
    ToolTimeoutError,
)
from ..infra.http_client import get_shared_http_client
from ..infra.upstream import timed_upstream_call
from ..observability import record_cache_hit

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


def _trusted_redirect_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.username is None
        and parsed.password is None
        and (
            host == "b23.tv" or host == "bilibili.com" or host.endswith(".bilibili.com")
        )
    )


def _video_destination(url: str) -> str | None:
    if not _trusted_redirect_url(url) or _is_b23_short_url(url):
        return None
    path = urlparse(url).path
    if not path.startswith("/video/"):
        return None
    return _extract_local_bvid(path)


@alru_cache(maxsize=128, ttl=300)
@without_request_deadline
async def _resolve_short_link_cached(text: str) -> tuple[str, str]:
    try:
        async with asyncio.timeout(SHORT_LINK_TIMEOUT_SECONDS):
            current = text
            visited: set[str] = set()
            for _ in range(5):
                if current in visited or not _trusted_redirect_url(current):
                    break
                visited.add(current)
                response = await timed_upstream_call(
                    get_shared_http_client().head(current, follow_redirects=False)
                )
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        break
                    current = urljoin(current, location)
                    resolved = _video_destination(current)
                    if resolved:
                        return resolved, current
                    continue

                response.raise_for_status()
                final_url = str(response.url)
                resolved = _video_destination(final_url)
                if resolved:
                    return resolved, final_url
                break
    except ToolTimeoutError:
        raise
    except Exception:
        # Keep URLs and transport exception details out of public errors/logs.
        raise ShortLinkResolutionError() from None
    raise ShortLinkResolutionError()


async def _resolve_video_input(raw: str) -> tuple[str, str]:
    text = raw.strip()
    if _is_b23_short_url(text):
        before = _resolve_short_link_cached.cache_info()
        result = await wait_cached(_resolve_short_link_cached, text)
        after = _resolve_short_link_cached.cache_info()
        record_cache_hit("short_link", after.hits > before.hits)
        return result

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
