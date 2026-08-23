import contextvars
import time
from typing import Any

_metrics_state_var: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar(
        "metrics_state",
        default=None,
    )
)

# Process-wide monotonic timestamps of recent risk-control responses
# (412/429/403), consulted by the adaptive upstream-jitter heuristic.
_risk_pressure_events: list[float] = []


def _new_state(request_id: str | None = None) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "retry_count": 0,
        "upstream_duration_ms": 0.0,
        "upstream_call_count": 0,
        "throttle_sleep_ms": 0.0,
        "lazy_pause_count": 0,
        "lazy_pause_ms": 0.0,
        "upstream_block_count": 0,
        "upstream_rate_limit_count": 0,
        "cache_stats": {},
    }


def _get_state() -> dict[str, Any]:
    state = _metrics_state_var.get()
    if state is None:
        state = _new_state()
        _metrics_state_var.set(state)
    return state


def begin_request(request_id: str) -> None:
    _metrics_state_var.set(_new_state(request_id=request_id))


def get_request_id() -> str | None:
    request_id = _get_state()["request_id"]
    return request_id if isinstance(request_id, str) else None


def add_retry() -> None:
    _get_state()["retry_count"] += 1


def register_upstream_call() -> int:
    state = _get_state()
    state["upstream_call_count"] += 1
    return int(state["upstream_call_count"])


def add_upstream_duration_ms(duration_ms: float) -> None:
    _get_state()["upstream_duration_ms"] += max(0.0, duration_ms)


def add_throttle_sleep_ms(duration_ms: float) -> None:
    _get_state()["throttle_sleep_ms"] += max(0.0, duration_ms)


def get_throttle_sleep_ms() -> float:
    return float(_get_state()["throttle_sleep_ms"])


def record_risk_pressure() -> None:
    """Mark a risk-control response (412/429/403) as recent."""
    now = time.monotonic()
    _risk_pressure_events.append(now)
    del _risk_pressure_events[: max(0, len(_risk_pressure_events) - 64)]


def recent_risk_pressure(window_seconds: float) -> bool:
    """True when a risk-control response occurred within the window."""
    if window_seconds <= 0 or not _risk_pressure_events:
        return False

    cutoff = time.monotonic() - window_seconds
    # Events are appended in time order, so stale ones form a prefix.
    stale_count = len([e for e in _risk_pressure_events if e < cutoff])
    del _risk_pressure_events[:stale_count]
    return bool(_risk_pressure_events)


def reset_risk_pressure() -> None:
    _risk_pressure_events.clear()


def add_lazy_pause(duration_ms: float) -> None:
    state = _get_state()
    state["lazy_pause_count"] += 1
    state["lazy_pause_ms"] += max(0.0, duration_ms)


def record_upstream_block() -> None:
    _get_state()["upstream_block_count"] += 1


def record_upstream_rate_limit() -> None:
    _get_state()["upstream_rate_limit_count"] += 1


def record_cache_hit(cache_name: str, hit: bool) -> None:
    state = _get_state()
    stats = state["cache_stats"]
    item = stats.setdefault(cache_name, {"hit": 0, "miss": 0})
    if hit:
        item["hit"] += 1
    else:
        item["miss"] += 1


def _summarize_cache_stats(
    raw_stats: dict[str, dict[str, int]],
) -> dict[str, dict[str, float | int]]:
    summary: dict[str, dict[str, float | int]] = {}
    for cache_name, item in raw_stats.items():
        hit = int(item.get("hit", 0))
        miss = int(item.get("miss", 0))
        total = hit + miss
        hit_rate = round((hit / total) if total > 0 else 0.0, 4)
        summary[cache_name] = {
            "hit": hit,
            "miss": miss,
            "total": total,
            "hit_rate": hit_rate,
        }
    return summary


def snapshot_metrics() -> dict[str, Any]:
    state = _get_state()
    cache_stats = _summarize_cache_stats(state["cache_stats"])
    return {
        "request_id": state["request_id"],
        "retry_count": state["retry_count"],
        "upstream_duration_ms": round(float(state["upstream_duration_ms"]), 3),
        "upstream_call_count": int(state["upstream_call_count"]),
        "throttle_sleep_ms": round(float(state["throttle_sleep_ms"]), 3),
        "lazy_pause_count": int(state["lazy_pause_count"]),
        "lazy_pause_ms": round(float(state["lazy_pause_ms"]), 3),
        "upstream_block_count": int(state["upstream_block_count"]),
        "upstream_rate_limit_count": int(state["upstream_rate_limit_count"]),
        "cache": cache_stats,
    }
