"""Subtitle collection and track selection for Bilibili videos."""

import asyncio
import logging
from typing import Any, Literal

from bilibili_api import Credential, video

from ..infra.http_client import get_json
from ..infra.upstream import timed_upstream_call
from ..models import SubtitleResponse, SubtitleTrack
from ..retry import RetryableBiliApiError
from ..utils.converters import coerce_int

logger = logging.getLogger(__name__)

SubtitleMode = Literal["minimal", "smart", "full"]
SUBTITLE_FETCH_CONCURRENCY = 4
DEFAULT_SUBTITLE_MODE: SubtitleMode = "smart"
DEFAULT_SUBTITLE_LANG = "auto"
DEFAULT_SUBTITLE_MAX_CHARS = 12000
DEFAULT_SUBTITLE_LANGUAGE_PRIORITY = (
    "zh-cn",
    "zh-hans",
    "zh-hant",
    "ai-zh",
    "en-us",
    "en",
    "ai-en",
)


def _normalize_subtitle_url(subtitle_url: object) -> str | None:
    if not isinstance(subtitle_url, str) or not subtitle_url:
        return None

    value = subtitle_url.strip()
    if not value:
        return None

    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value.lstrip('/')}"


async def _fetch_subtitle_text(
    subtitle_url: Any,
    cred: Credential | None,
) -> tuple[str, str | None]:
    url = _normalize_subtitle_url(subtitle_url)
    if not url:
        return "", "subtitle_url missing"

    try:
        subtitle_payload = await get_json(url, cred=cred)

        body = subtitle_payload.get("body") or []
        lines: list[str] = []
        for item in body:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                lines.append(content.strip())

        return "\n".join(lines), None
    except RetryableBiliApiError as exc:
        return "", f"blocked or rate-limited: {exc}"
    except Exception as exc:
        return "", str(exc)


def _normalize_language_tag(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def _build_track_metadata(
    cid: int,
    part: str | None,
    subtitle_item: dict[str, Any],
) -> tuple[SubtitleTrack, str | None]:
    lan = (
        subtitle_item.get("lan") if isinstance(subtitle_item.get("lan"), str) else None
    )
    lan_doc = (
        subtitle_item.get("lan_doc")
        if isinstance(subtitle_item.get("lan_doc"), str)
        else None
    )

    is_ai_generated = bool(
        (isinstance(lan, str) and lan.startswith("ai-"))
        or (coerce_int(subtitle_item.get("ai_type")) or 0) > 0
        or (coerce_int(subtitle_item.get("ai_status")) or 0) > 0
    )

    track = SubtitleTrack(
        cid=cid,
        part=part,
        lan=lan,
        lan_doc=lan_doc,
        is_ai_generated=is_ai_generated,
        text="",
    )
    subtitle_url = subtitle_item.get("subtitle_url")
    return track, subtitle_url


def _append_track_with_budget(
    track: SubtitleTrack,
    raw_text: str,
    selected_tracks: list[SubtitleTrack],
    full_text_lines: list[str],
    remaining_budget: int,
) -> tuple[int, bool]:
    text = raw_text or ""
    was_truncated = False
    if text:
        separator_cost = 1 if full_text_lines else 0
        if remaining_budget <= separator_cost:
            text = ""
            was_truncated = True
        else:
            remaining_budget -= separator_cost
            if len(text) > remaining_budget:
                text = text[:remaining_budget]
                remaining_budget = 0
                was_truncated = True
            else:
                remaining_budget -= len(text)

    selected_tracks.append(track.model_copy(update={"text": text}))
    if text:
        full_text_lines.append(text)
    return remaining_budget, was_truncated


def _build_subtitle_candidates(
    cid: int,
    part: str | None,
    subtitle_items: Any,
    *,
    require_complete: bool = False,
) -> list[dict[str, Any]] | None:
    if not isinstance(subtitle_items, list):
        return None if require_complete else []

    candidates: list[dict[str, Any]] = []
    for subtitle_item in subtitle_items:
        if not isinstance(subtitle_item, dict):
            if require_complete:
                return None
            continue

        track, subtitle_url = _build_track_metadata(
            cid=cid,
            part=part,
            subtitle_item=subtitle_item,
        )
        normalized_url = _normalize_subtitle_url(subtitle_url)
        if require_complete and (
            not isinstance(track.lan, str)
            or not track.lan.strip()
            or normalized_url is None
        ):
            return None

        candidates.append(
            {"track": track, "subtitle_url": normalized_url or subtitle_url}
        )

    if require_complete and not candidates:
        return None

    return candidates


def _extract_inline_subtitle_candidates(
    video_info: dict[str, Any] | None,
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    if not isinstance(video_info, dict) or len(pages) != 1:
        return None

    subtitle_meta = video_info.get("subtitle")
    if not isinstance(subtitle_meta, dict):
        return None

    page = pages[0]
    cid = coerce_int(page.get("cid"))
    if cid is None:
        return None

    part = page.get("part")
    part_value = part if isinstance(part, str) else None

    return _build_subtitle_candidates(
        cid=cid,
        part=part_value,
        subtitle_items=subtitle_meta.get("list"),
        require_complete=True,
    )


def _select_smart_subtitle_candidate(
    candidates: list[dict[str, Any]],
    requested_language: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if not candidates:
        return None, None

    requested_raw = (
        requested_language.strip() if isinstance(requested_language, str) else ""
    )
    requested_norm = _normalize_language_tag(requested_raw)
    normalized_auto = _normalize_language_tag(DEFAULT_SUBTITLE_LANG)

    if requested_norm and requested_norm != normalized_auto:
        for candidate in candidates:
            lan_norm = _normalize_language_tag(candidate["track"].lan)
            if lan_norm == requested_norm:
                return candidate, None

        for candidate in candidates:
            lan_norm = _normalize_language_tag(candidate["track"].lan)
            if lan_norm and (
                lan_norm.startswith(f"{requested_norm}-")
                or requested_norm.startswith(f"{lan_norm}-")
            ):
                selected = candidate["track"].lan or "unknown"
                return (
                    candidate,
                    f"requested '{requested_raw}' not exact; matched '{selected}'",
                )

    for preferred in DEFAULT_SUBTITLE_LANGUAGE_PRIORITY:
        for candidate in candidates:
            lan_norm = _normalize_language_tag(candidate["track"].lan)
            if lan_norm == preferred:
                if requested_norm and requested_norm != normalized_auto:
                    selected = candidate["track"].lan or "unknown"
                    return (
                        candidate,
                        f"requested '{requested_raw}' unavailable; fallback to '{selected}'",
                    )
                return candidate, None

    fallback_candidate = candidates[0]
    selected = fallback_candidate["track"].lan or "unknown"
    if requested_norm and requested_norm != normalized_auto:
        return (
            fallback_candidate,
            f"requested '{requested_raw}' unavailable; fallback to '{selected}'",
        )
    return (
        fallback_candidate,
        "auto preference not matched; fallback to first available",
    )


def build_disabled_subtitles(subtitle_lang: str) -> SubtitleResponse:
    return SubtitleResponse(
        enabled=False,
        mode="disabled",
        requested_language=(
            subtitle_lang if isinstance(subtitle_lang, str) else DEFAULT_SUBTITLE_LANG
        ),
        available_languages=[],
        selected_language=None,
        fallback_reason=None,
        truncated=False,
        returned_chars=0,
        dropped_tracks=0,
        track_count=0,
        tracks=[],
        full_text="",
        errors=[],
    )


async def collect_subtitles(
    video_client: video.Video,
    pages: list[dict[str, Any]],
    cred: Credential | None,
    subtitle_mode: SubtitleMode = DEFAULT_SUBTITLE_MODE,
    subtitle_lang: str = DEFAULT_SUBTITLE_LANG,
    subtitle_max_chars: int = DEFAULT_SUBTITLE_MAX_CHARS,
    *,
    video_info: dict[str, Any] | None = None,
) -> SubtitleResponse:
    mode = subtitle_mode.strip().lower() if isinstance(subtitle_mode, str) else ""
    if mode == "minimal":
        normalized_mode: SubtitleMode = "minimal"
    elif mode == "full":
        normalized_mode = "full"
    else:
        normalized_mode = "smart"

    if normalized_mode == "minimal":
        return SubtitleResponse(
            enabled=True,
            mode=normalized_mode,
            requested_language=(
                subtitle_lang
                if isinstance(subtitle_lang, str)
                else DEFAULT_SUBTITLE_LANG
            ),
            available_languages=[],
            selected_language=None,
            fallback_reason="subtitle metadata and text skipped by mode=minimal",
            truncated=False,
            returned_chars=0,
            dropped_tracks=0,
            track_count=0,
            tracks=[],
            full_text="",
            errors=[],
        )

    char_budget = (
        subtitle_max_chars
        if isinstance(subtitle_max_chars, int)
        else DEFAULT_SUBTITLE_MAX_CHARS
    )
    if char_budget < 1:
        char_budget = DEFAULT_SUBTITLE_MAX_CHARS

    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    semaphore = asyncio.Semaphore(SUBTITLE_FETCH_CONCURRENCY)

    async def _timed_get_subtitle(cid: int) -> dict[str, Any]:
        async with semaphore:
            return await timed_upstream_call(video_client.get_subtitle(cid=cid))

    async def _timed_fetch_track_text(subtitle_url: Any) -> tuple[str, str | None]:
        async with semaphore:
            return await _fetch_subtitle_text(subtitle_url, cred)

    async def _collect_page_tracks(
        page: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        page_tracks: list[dict[str, Any]] = []
        page_errors: list[str] = []

        cid = coerce_int(page.get("cid"))
        part = page.get("part")
        part_value = part if isinstance(part, str) else None

        if cid is None:
            page_errors.append("page without cid")
            return page_tracks, page_errors

        try:
            subtitle_data = await _timed_get_subtitle(cid)
        except Exception as exc:
            page_errors.append(f"cid {cid}: subtitle metadata failed: {exc}")
            return page_tracks, page_errors

        subtitle_items = (subtitle_data or {}).get("subtitles") or []
        if not isinstance(subtitle_items, list):
            page_errors.append(f"cid {cid}: invalid subtitle payload")
            return page_tracks, page_errors

        for subtitle_item in subtitle_items:
            if not isinstance(subtitle_item, dict):
                continue
            track, subtitle_url = _build_track_metadata(
                cid=cid,
                part=part_value,
                subtitle_item=subtitle_item,
            )
            page_tracks.append({"track": track, "subtitle_url": subtitle_url})

        return page_tracks, page_errors

    inline_candidates = None
    if normalized_mode == "smart":
        inline_candidates = _extract_inline_subtitle_candidates(video_info, pages)

    if inline_candidates is not None:
        candidates.extend(inline_candidates)
    else:
        page_tasks = [_collect_page_tracks(page) for page in pages]
        for page_tracks, page_errors in await asyncio.gather(*page_tasks):
            candidates.extend(page_tracks)
            errors.extend(page_errors)

    available_languages: list[str] = []
    seen_languages: set[str] = set()
    for candidate in candidates:
        lan = candidate["track"].lan
        lan_norm = _normalize_language_tag(lan)
        if not lan_norm or lan_norm in seen_languages:
            continue
        seen_languages.add(lan_norm)
        available_languages.append(lan or lan_norm)

    if not candidates:
        return SubtitleResponse(
            enabled=True,
            mode=normalized_mode,
            requested_language=(
                subtitle_lang
                if isinstance(subtitle_lang, str)
                else DEFAULT_SUBTITLE_LANG
            ),
            available_languages=available_languages,
            selected_language=None,
            fallback_reason="No subtitle tracks available",
            truncated=False,
            returned_chars=0,
            dropped_tracks=0,
            track_count=0,
            tracks=[],
            full_text="",
            errors=errors,
        )

    selected_tracks: list[SubtitleTrack] = []
    full_text_lines: list[str] = []
    truncated = False
    dropped_tracks = 0
    selected_language: str | None = None
    fallback_reason: str | None = None

    if normalized_mode == "smart":
        selected_candidate, fallback_reason = _select_smart_subtitle_candidate(
            candidates=candidates,
            requested_language=subtitle_lang,
        )
        if selected_candidate is None:
            return SubtitleResponse(
                enabled=True,
                mode=normalized_mode,
                requested_language=(
                    subtitle_lang
                    if isinstance(subtitle_lang, str)
                    else DEFAULT_SUBTITLE_LANG
                ),
                available_languages=available_languages,
                selected_language=None,
                fallback_reason="No subtitle tracks available",
                truncated=False,
                returned_chars=0,
                dropped_tracks=0,
                track_count=0,
                tracks=[],
                full_text="",
                errors=errors,
            )

        text, error = await _timed_fetch_track_text(selected_candidate["subtitle_url"])
        if error:
            track = selected_candidate["track"]
            errors.append(
                f"cid {track.cid} {track.lan_doc or track.lan or 'unknown'}: {error}"
            )

        remaining_budget = char_budget
        remaining_budget, was_truncated = _append_track_with_budget(
            track=selected_candidate["track"],
            raw_text=text,
            selected_tracks=selected_tracks,
            full_text_lines=full_text_lines,
            remaining_budget=remaining_budget,
        )
        _ = remaining_budget
        truncated = truncated or was_truncated
        dropped_tracks = max(0, len(candidates) - len(selected_tracks))
        selected_language = selected_candidate["track"].lan
    else:
        track_tasks = [
            _timed_fetch_track_text(candidate["subtitle_url"])
            for candidate in candidates
        ]
        track_results = await asyncio.gather(*track_tasks)
        remaining_budget = char_budget
        for candidate, (text, error) in zip(candidates, track_results):
            track = candidate["track"]
            if error:
                errors.append(
                    f"cid {track.cid} {track.lan_doc or track.lan or 'unknown'}: {error}"
                )
            remaining_budget, was_truncated = _append_track_with_budget(
                track=track,
                raw_text=text,
                selected_tracks=selected_tracks,
                full_text_lines=full_text_lines,
                remaining_budget=remaining_budget,
            )
            truncated = truncated or was_truncated
        dropped_tracks = max(0, len(candidates) - len(selected_tracks))

    full_text = "\n".join(full_text_lines)

    return SubtitleResponse(
        enabled=True,
        mode=normalized_mode,
        requested_language=(
            subtitle_lang if isinstance(subtitle_lang, str) else DEFAULT_SUBTITLE_LANG
        ),
        available_languages=available_languages,
        selected_language=selected_language,
        fallback_reason=fallback_reason,
        truncated=truncated,
        returned_chars=len(full_text),
        dropped_tracks=dropped_tracks,
        track_count=len(selected_tracks),
        tracks=selected_tracks,
        full_text=full_text,
        errors=errors,
    )
