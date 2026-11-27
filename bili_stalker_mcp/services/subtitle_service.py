"""Subtitle collection and track selection for Bilibili videos."""

import asyncio
import logging
from typing import Any, Literal

from bilibili_api import Credential, video

from ..errors import RiskControlError, public_error_json
from ..infra.http_client import get_json
from ..infra.upstream import timed_upstream_call
from ..models import SubtitleResponse, SubtitleScopeSummary, SubtitleTrack
from ..retry import RetryableBiliApiError, with_retry
from ..utils.converters import coerce_int
from .subtitle_output import (
    SubtitleCue,
    SubtitleOutput,
    SubtitleOutputOptions,
    subtitle_seconds,
)

logger = logging.getLogger(__name__)

SubtitleMode = Literal["minimal", "smart", "full"]
SubtitleScope = Literal["single", "all"]
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
SUBTITLE_LOGIN_REQUIRED_REASON = (
    "Bilibili requires a valid login to return subtitle tracks; "
    "configured SESSDATA was not authenticated"
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


@with_retry(max_retries=2, base_delay=0.5, max_delay=2.0)
async def _fetch_subtitle_payload(
    url: str,
    cred: Credential | None,
) -> dict[str, Any]:
    return await get_json(url, cred=cred)


async def _fetch_subtitle_cues(
    subtitle_url: Any,
    cred: Credential | None,
) -> tuple[list[SubtitleCue] | None, str | None]:
    url = _normalize_subtitle_url(subtitle_url)
    if not url:
        return None, "subtitle_url missing"

    try:
        subtitle_payload = await _fetch_subtitle_payload(url, cred)

        body = subtitle_payload.get("body") or []
        cues: list[SubtitleCue] = []
        for item in body:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, str):
                continue
            text = content.strip()
            if not text:
                continue
            start = subtitle_seconds(item.get("from"))
            end = subtitle_seconds(item.get("to"))
            timing = (
                (start, end)
                if start is not None and end is not None and start < end
                else None
            )
            cues.append(SubtitleCue(text, timing))

        return cues, None
    except RiskControlError as exc:
        return None, public_error_json(exc)
    except RetryableBiliApiError as exc:
        return None, f"blocked or rate-limited: {public_error_json(exc)}"
    except Exception as exc:
        return None, str(exc)


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


def _track_label(track: SubtitleTrack) -> str:
    language = track.lan_doc or track.lan or "unknown"
    if track.part:
        return f"{language} · {track.part}"
    return language


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
) -> tuple[dict[str, Any], str | None]:
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


def _summarize_scope(
    scope: SubtitleScopeSummary | None,
    returned_pages: set[int],
    *,
    skipped: bool = False,
) -> SubtitleScopeSummary | None:
    if scope is None:
        return None
    selected = (
        f"P{scope.target_page} of {scope.total_pages} pages"
        if scope.mode == "single"
        else f"all {scope.total_pages} pages"
    )
    if skipped:
        text_summary = "Subtitle metadata and text skipped by mode=minimal."
    elif len(returned_pages) == 1:
        text_summary = f"Text returned for P{next(iter(returned_pages))}."
    else:
        text_summary = f"Text returned for {len(returned_pages)} pages."
    uncovered = scope.total_pages - len(returned_pages)
    return scope.model_copy(
        update={
            "returned_pages": sorted(returned_pages),
            "summary": (
                f"Selected scope: {selected}. {text_summary} "
                f"{uncovered} of {scope.total_pages} pages have no returned text. "
                "Check errors and truncated for completeness."
            ),
        }
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
    scope: SubtitleScopeSummary | None = None,
    output_options: SubtitleOutputOptions = SubtitleOutputOptions(),
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
            scope=_summarize_scope(scope, set(), skipped=True),
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
    page_numbers: dict[int, int] = {}
    for page in pages:
        cid = coerce_int(page.get("cid"))
        page_number = coerce_int(page.get("page"))
        if cid is not None and page_number is not None:
            page_numbers[cid] = page_number
    returned_pages: set[int] = set()
    semaphore = asyncio.Semaphore(SUBTITLE_FETCH_CONCURRENCY)

    async def _timed_get_player_info(cid: int) -> dict[str, Any]:
        async with semaphore:
            return await timed_upstream_call(video_client.get_player_info(cid=cid))

    async def _timed_fetch_track_cues(
        subtitle_url: Any,
    ) -> tuple[list[SubtitleCue] | None, str | None]:
        async with semaphore:
            return await _fetch_subtitle_cues(subtitle_url, cred)

    async def _collect_page_tracks(
        page: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        page_tracks: list[dict[str, Any]] = []
        page_errors: list[str] = []

        cid = coerce_int(page.get("cid"))
        part = page.get("part")
        part_value = part if isinstance(part, str) else None

        if cid is None:
            page_errors.append("page without cid")
            return page_tracks, page_errors, False

        try:
            player_info = await _timed_get_player_info(cid)
        except Exception as exc:
            page_errors.append(f"cid {cid}: subtitle metadata failed: {exc}")
            return page_tracks, page_errors, False

        login_mid = coerce_int(player_info.get("login_mid"))
        login_required = bool(player_info.get("need_login_subtitle")) and not login_mid
        subtitle_data = player_info.get("subtitle")
        if not isinstance(subtitle_data, dict):
            subtitle_data = {}

        subtitle_items = (subtitle_data or {}).get("subtitles") or []
        if not isinstance(subtitle_items, list):
            page_errors.append(f"cid {cid}: invalid subtitle payload")
            return page_tracks, page_errors, login_required

        if login_required and not subtitle_items:
            page_errors.append(f"cid {cid}: {SUBTITLE_LOGIN_REQUIRED_REASON}")

        for subtitle_item in subtitle_items:
            if not isinstance(subtitle_item, dict):
                continue
            track, subtitle_url = _build_track_metadata(
                cid=cid,
                part=part_value,
                subtitle_item=subtitle_item,
            )
            page_tracks.append({"track": track, "subtitle_url": subtitle_url})

        return page_tracks, page_errors, login_required

    inline_candidates = None
    login_required = False
    if normalized_mode == "smart":
        inline_candidates = _extract_inline_subtitle_candidates(video_info, pages)

    if inline_candidates is not None:
        candidates.extend(inline_candidates)
    else:
        page_tasks = [_collect_page_tracks(page) for page in pages]
        for page_tracks, page_errors, page_login_required in await asyncio.gather(
            *page_tasks
        ):
            candidates.extend(page_tracks)
            errors.extend(page_errors)
            login_required = login_required or page_login_required

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
            scope=_summarize_scope(scope, returned_pages),
            requested_language=(
                subtitle_lang
                if isinstance(subtitle_lang, str)
                else DEFAULT_SUBTITLE_LANG
            ),
            available_languages=available_languages,
            selected_language=None,
            fallback_reason=(
                SUBTITLE_LOGIN_REQUIRED_REASON
                if login_required
                else "No subtitle tracks available"
            ),
            truncated=False,
            returned_chars=0,
            dropped_tracks=0,
            track_count=0,
            tracks=[],
            full_text="",
            errors=errors,
        )

    output = SubtitleOutput(output_options, char_budget)
    selected_language: str | None = None
    fallback_reason: str | None = None

    if normalized_mode == "smart":
        selected_candidate, fallback_reason = _select_smart_subtitle_candidate(
            candidates=candidates,
            requested_language=subtitle_lang,
        )
        selected_language = selected_candidate["track"].lan
        selected_candidates = [selected_candidate]
        track_results = [
            await _timed_fetch_track_cues(selected_candidate["subtitle_url"])
        ]
    else:
        selected_candidates = candidates
        track_results = await asyncio.gather(
            *(
                _timed_fetch_track_cues(candidate["subtitle_url"])
                for candidate in candidates
            )
        )
    use_labels = normalized_mode == "full" and len(candidates) > 1

    for candidate, (cues, error) in zip(selected_candidates, track_results):
        track = candidate["track"]
        language = track.lan_doc or track.lan or "unknown"
        if error:
            errors.append(f"cid {track.cid} {language}: {error}")
        if output_options.format != "text" and cues:
            invalid = sum(cue.timing is None for cue in cues)
            if invalid:
                errors.append(
                    f"cid {track.cid} {language}: {invalid} subtitle cues have missing or invalid timestamps"
                )
        if output.append_track(
            track, cues, _track_label(track) if use_labels else None
        ):
            page_number = page_numbers.get(track.cid) if track.cid is not None else None
            if page_number is not None:
                returned_pages.add(page_number)
    if output_options.format == "anchors":
        output.limit_anchors()

    return SubtitleResponse(
        enabled=True,
        mode=normalized_mode,
        scope=_summarize_scope(scope, returned_pages),
        requested_language=(
            subtitle_lang if isinstance(subtitle_lang, str) else DEFAULT_SUBTITLE_LANG
        ),
        available_languages=available_languages,
        selected_language=selected_language,
        fallback_reason=fallback_reason,
        truncated=output.truncated,
        returned_chars=output.returned_chars,
        dropped_tracks=len(candidates) - len(output.tracks),
        track_count=len(output.tracks),
        tracks=output.tracks,
        full_text=output.full_text,
        errors=errors,
    )
