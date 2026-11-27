"""Render subtitle cues and enforce response budgets across tracks."""

import math
from dataclasses import dataclass

from ..errors import InvalidSubtitleSelectionError
from ..models import (
    SubtitleAnchor,
    SubtitleCoverage,
    SubtitleFormat,
    SubtitleSegment,
    SubtitleTrack,
)

DEFAULT_ANCHOR_INTERVAL_SEC = 30
MAX_SUBTITLE_ANCHORS = 1000
MAX_SUBTITLE_SEGMENTS = 5000


def subtitle_seconds(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        seconds = float(value)
    except OverflowError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


@dataclass(frozen=True)
class SubtitleOutputOptions:
    format: SubtitleFormat = "text"
    anchor_interval_sec: int | None = None
    anchor_interval_lines: int | None = None
    start_sec: float | None = None
    end_sec: float | None = None

    def validate(self, *, mode: str, scope: str) -> None:
        if self.format not in {"text", "anchors", "segments"}:
            raise InvalidSubtitleSelectionError(
                "subtitle_format must be text, anchors, or segments."
            )
        if (
            self.format != "text"
            and isinstance(mode, str)
            and mode.strip().lower() == "minimal"
        ):
            raise InvalidSubtitleSelectionError(
                "Subtitle timing requires subtitle_mode=smart or full."
            )
        if (
            self.anchor_interval_sec is not None
            and self.anchor_interval_lines is not None
        ):
            raise InvalidSubtitleSelectionError(
                "subtitle_anchor_interval_sec and subtitle_anchor_interval_lines are mutually exclusive."
            )
        for name, interval in (
            ("subtitle_anchor_interval_sec", self.anchor_interval_sec),
            ("subtitle_anchor_interval_lines", self.anchor_interval_lines),
        ):
            if interval is None:
                continue
            if self.format != "anchors":
                raise InvalidSubtitleSelectionError(
                    f"{name} requires subtitle_format=anchors."
                )
            if (
                isinstance(interval, bool)
                or not isinstance(interval, int)
                or interval < 1
            ):
                raise InvalidSubtitleSelectionError(
                    f"{name} must be a positive integer."
                )
        if self.start_sec is None and self.end_sec is None:
            return
        if self.format != "segments" or scope != "single":
            raise InvalidSubtitleSelectionError(
                "A subtitle time range requires subtitle_format=segments and subtitle_scope=single."
            )
        for name, value in (
            ("subtitle_start_sec", self.start_sec),
            ("subtitle_end_sec", self.end_sec),
        ):
            if value is not None and subtitle_seconds(value) is None:
                raise InvalidSubtitleSelectionError(
                    f"{name} must be finite and nonnegative."
                )
        if self.end_sec is not None and self.end_sec <= (self.start_sec or 0):
            raise InvalidSubtitleSelectionError(
                "subtitle_end_sec must be greater than the start time."
            )


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    text: str
    timing: tuple[float, float] | None = None


def _coverage(
    source: list[SubtitleCue], returned: list[SubtitleCue]
) -> SubtitleCoverage:
    source_times = [cue.timing for cue in source if cue.timing is not None]
    returned_times = [cue.timing for cue in returned if cue.timing is not None]
    return SubtitleCoverage(
        source_start_sec=min((start for start, _ in source_times), default=None),
        source_end_sec=max((end for _, end in source_times), default=None),
        returned_start_sec=min((start for start, _ in returned_times), default=None),
        returned_end_sec=max((end for _, end in returned_times), default=None),
        returned_cues=len(returned),
    )


class SubtitleOutput:
    def __init__(self, options: SubtitleOutputOptions, char_budget: int) -> None:
        self.options = options
        self.char_budget = char_budget
        self.tracks: list[SubtitleTrack] = []
        self.truncated = False
        self.returned_chars = 0
        self._text_blocks: list[str] = []
        self._next_line = 1
        self._segment_count = 0

    @property
    def full_text(self) -> str:
        return "\n".join(self._text_blocks)

    def append_track(
        self, track: SubtitleTrack, cues: list[SubtitleCue] | None, label: str | None
    ) -> bool:
        self.tracks.append(track)
        if cues is None:
            return False
        if self.options.format == "segments":
            return self._append_segments(track, cues)
        return self._append_text(track, cues, label)

    def _append_text(
        self, track: SubtitleTrack, cues: list[SubtitleCue], label: str | None
    ) -> bool:
        text = "\n".join(cue.text for cue in cues)
        header = f"[{label}]\n" if label else ""
        overhead = len(header) + bool(self._text_blocks)
        available = max(0, self.char_budget - self.returned_chars - overhead)
        returned = text[:available]
        self.truncated |= len(returned) < len(text)
        first_line = self._next_line + header.count("\n")
        if returned:
            block = header + returned
            self._text_blocks.append(block)
            self._next_line += block.count("\n") + 1
            self.returned_chars += len(returned) + overhead
        if self.options.format == "anchors":
            self._set_track_anchors(track, cues, len(returned), first_line)
        return bool(returned)

    def _set_track_anchors(
        self,
        track: SubtitleTrack,
        cues: list[SubtitleCue],
        returned_chars: int,
        first_line: int,
    ) -> None:
        returned: list[SubtitleCue] = []
        anchors: list[SubtitleAnchor] = []
        seen_windows: set[int] = set()
        local_line = 0
        offset = 0
        last_anchor = None
        interval_lines = self.options.anchor_interval_lines
        interval_sec = self.options.anchor_interval_sec or DEFAULT_ANCHOR_INTERVAL_SEC
        for cue in cues:
            if offset >= returned_chars:
                break
            returned.append(cue)
            if cue.timing is not None:
                start, _ = cue.timing
                window = (
                    local_line // interval_lines
                    if interval_lines
                    else int(start) // interval_sec
                )
                last_anchor = (first_line + local_line, start)
                if window not in seen_windows:
                    seen_windows.add(window)
                    anchors.append(last_anchor)
            offset += len(cue.text) + 1
            local_line += cue.text.count("\n") + 1

        if last_anchor is not None and last_anchor != anchors[-1]:
            anchors.append(last_anchor)
        track.anchors = anchors
        track.coverage = _coverage(cues, returned)

    def _append_segments(self, track: SubtitleTrack, cues: list[SubtitleCue]) -> bool:
        returned: list[SubtitleCue] = []
        segments: list[SubtitleSegment] = []
        window_start = self.options.start_sec or 0
        window_end = (
            self.options.end_sec if self.options.end_sec is not None else math.inf
        )
        for cue in cues:
            if cue.timing is None:
                continue
            start, end = cue.timing
            if start >= window_end or end <= window_start:
                continue
            if (
                self.truncated
                or self._segment_count >= MAX_SUBTITLE_SEGMENTS
                or self.returned_chars + len(cue.text) > self.char_budget
            ):
                self.truncated = True
                break
            segments.append(
                SubtitleSegment(start_sec=start, end_sec=end, text=cue.text)
            )
            returned.append(cue)
            self._segment_count += 1
            self.returned_chars += len(cue.text)
        track.segments = segments
        track.coverage = _coverage(cues, returned)
        return bool(segments)

    def limit_anchors(self) -> None:
        indexed_tracks = [
            (track, track.anchors) for track in self.tracks if track.anchors
        ]
        if sum(len(anchors) for _, anchors in indexed_tracks) <= MAX_SUBTITLE_ANCHORS:
            return

        kept: list[list[SubtitleAnchor]] = [[] for _ in indexed_tracks]
        interior: list[tuple[int, SubtitleAnchor]] = []
        slots = MAX_SUBTITLE_ANCHORS
        for index, (_, anchors) in enumerate(indexed_tracks):
            endpoints = anchors if len(anchors) <= 2 else [anchors[0], anchors[-1]]
            if len(endpoints) <= slots:
                kept[index].extend(endpoints)
                slots -= len(endpoints)
                interior.extend((index, anchor) for anchor in anchors[1:-1])
        interior_count = min(len(interior), slots)
        for index in range(interior_count):
            # Pick the midpoint of each equal-sized slice of interior anchors.
            sample = (2 * index + 1) * len(interior) // (2 * interior_count)
            track_index, anchor = interior[sample]
            kept[track_index].append(anchor)
        for (track, anchors), retained in zip(indexed_tracks, kept):
            track.anchors = sorted(retained)
            track.anchors_truncated = len(retained) < len(anchors)
