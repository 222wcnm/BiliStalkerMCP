import contextvars
from typing import Any

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)
_retry_count_var: contextvars.ContextVar[int] = contextvars.ContextVar(
    "retry_count",
    default=0,
)
_upstream_ms_var: contextvars.ContextVar[float] = contextvars.ContextVar(
    "upstream_ms",
    default=0.0,
)
_cache_stats_var: contextvars.ContextVar[dict[str, dict[str, int]]] = contextvars.ContextVar(
    "cache_stats",
    default={},
)


def begin_request(request_id: str) -> None:
    _request_id_var.set(request_id)
    _retry_count_var.set(0)
    _upstream_ms_var.set(0.0)
    _cache_stats_var.set({})


def get_request_id() -> str | None:
    return _request_id_var.get()


def add_retry() -> None:
    _retry_count_var.set(_retry_count_var.get() + 1)


def add_upstream_duration_ms(duration_ms: float) -> None:
    _upstream_ms_var.set(_upstream_ms_var.get() + max(0.0, duration_ms))


def record_cache_hit(cache_name: str, hit: bool) -> None:
    stats = dict(_cache_stats_var.get())
    item = dict(stats.get(cache_name, {"hit": 0, "miss": 0}))
    if hit:
        item["hit"] += 1
    else:
        item["miss"] += 1
    stats[cache_name] = item
    _cache_stats_var.set(stats)


def _summarize_cache_stats(raw_stats: dict[str, dict[str, int]]) -> dict[str, dict[str, float | int]]:
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
    cache_stats = _summarize_cache_stats(_cache_stats_var.get())
    return {
        "request_id": _request_id_var.get(),
        "retry_count": _retry_count_var.get(),
        "upstream_duration_ms": round(_upstream_ms_var.get(), 3),
        "cache": cache_stats,
    }
