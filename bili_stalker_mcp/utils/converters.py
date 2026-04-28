"""Shared data-coercion utilities used across service and parser layers."""

from typing import Any

from bilibili_api import aid2bvid


def coerce_int(value: Any) -> int | None:
    """Coerce *value* to ``int``, returning ``None`` on failure."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def safe_aid_to_bvid(aid: Any) -> str | None:
    """Convert an AV-id to BV-id, suppressing all exceptions."""
    if not aid:
        return None
    try:
        return aid2bvid(aid)
    except Exception:
        return None
