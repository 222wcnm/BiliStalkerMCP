"""Controlled A/B benchmark: raw bilibili-api-python vs BiliStalkerMCP service layer.

Both groups run in one process, sharing the same event loop, credential, target
user, and the bilibili_api global request settings (headers/timeout/curl_cffi),
which are applied when ``bili_stalker_mcp.core`` is imported. Group order is
alternated per round to cancel network drift, and the same inter-call gap is
applied to both groups.

Deliberate anti-risk-control pacing (upstream jitter, dynamics lazy pause) is
disabled by default so the comparison isolates wrapper overhead. Export
BILI_PERF_KEEP_PACING=1 to keep the production pacing (used to quantify what
the pacing itself costs).

The MCP group clears its async-lru caches before every measured call (cold,
same upstream work as the raw group). Warm-cache and FastMCP protocol tiers
are measured separately at the end.

Usage:
    python scripts/perf_compare_raw.py -u <uid> [-n 5] [-l 10] [--gap 2.0]
"""

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

# Must happen before importing bili_stalker_mcp: config.py reads these at import.
if os.environ.get("BILI_PERF_KEEP_PACING") != "1":
    os.environ.setdefault("BILI_REQUEST_JITTER_MIN_MS", "0")
    os.environ.setdefault("BILI_REQUEST_JITTER_MAX_MS", "0")
    os.environ.setdefault("BILI_LAZY_ENABLED", "false")
else:
    # Reproduce the pre-adaptive default: unconditional jitter sleeps.
    os.environ.setdefault("BILI_REQUEST_JITTER_MODE", "always")

# Optional explicit proxy for all HTTP paths (bilibili_api's curl_cffi client
# overrides env proxies with an empty string, so it needs request_settings too).
BENCH_PROXY = os.environ.get("BILI_BENCH_PROXY", "")
if BENCH_PROXY:
    os.environ.setdefault("http_proxy", BENCH_PROXY)
    os.environ.setdefault("https_proxy", BENCH_PROXY)
    os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dev dependency normally present
    load_dotenv = None

from bili_stalker_mcp import core
from bili_stalker_mcp.services import user_service as _user_service

if BENCH_PROXY:
    from bilibili_api import request_settings

    request_settings.set_proxy(BENCH_PROXY)

from bili_stalker_mcp.observability import begin_request

TaskFn = Callable[[], Awaitable[object]]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare raw bilibili-api-python vs BiliStalkerMCP overhead."
    )
    parser.add_argument("-u", "--user", default="2", help="target UID (default: 2)")
    parser.add_argument("-n", "--iterations", type=int, default=5)
    parser.add_argument("-l", "--limit", type=int, default=10)
    parser.add_argument("--gap", type=float, default=2.0, help="seconds between calls")
    parser.add_argument(
        "--tasks",
        default="user_info,videos,dynamics,articles",
        help="comma-separated: user_info,videos,dynamics,articles",
    )
    return parser.parse_args()


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return float(ordered[round((len(ordered) - 1) * p)])


def _stats(samples_ms: list[float]) -> dict[str, float | int]:
    if not samples_ms:
        return {"count": 0}
    return {
        "count": len(samples_ms),
        "avg_ms": round(statistics.mean(samples_ms), 1),
        "p50_ms": round(_percentile(samples_ms, 0.5), 1),
        "p95_ms": round(_percentile(samples_ms, 0.95), 1),
        "min_ms": round(min(samples_ms), 1),
        "max_ms": round(max(samples_ms), 1),
    }


def _clear_caches() -> None:
    _user_service._fetch_user_info_cached.cache_clear()
    _user_service._fetch_video_detail_cached.cache_clear()
    _user_service._search_users_cached.cache_clear()


async def _build_tasks(uid: int, limit: int, cred) -> dict[str, dict[str, TaskFn]]:
    from bilibili_api import user

    def raw_user() -> user.User:
        return user.User(uid=uid, credential=cred)

    async def raw_user_info() -> object:
        u = raw_user()
        info, relation, up_stat = await asyncio.gather(
            u.get_user_info(), u.get_relation_info(), u.get_up_stat()
        )
        return {"info": info, "relation": relation, "up_stat": up_stat}

    return {
        "user_info": {
            "raw": raw_user_info,
            "mcp": lambda: core.fetch_user_info(uid, cred),
        },
        "videos": {
            "raw": lambda: raw_user().get_videos(pn=1, ps=limit),
            "mcp": lambda: core.fetch_user_videos(uid, 1, limit, cred),
        },
        "dynamics": {
            "raw": lambda: raw_user().get_dynamics_new(),
            "mcp": lambda: core.fetch_user_dynamics(
                user_id=uid, limit=limit, cred=cred, dynamic_type="ALL"
            ),
        },
        "articles": {
            "raw": lambda: raw_user().get_articles(pn=1, ps=limit),
            "mcp": lambda: core.fetch_user_articles(uid, 1, limit, cred),
        },
    }


async def _run_benchmark(
    tasks: dict[str, dict[str, TaskFn]],
    task_names: list[str],
    iterations: int,
    warmup: int,
    gap: float,
) -> tuple[
    dict[str, list[float]],
    dict[str, list[float]],
    dict[str, dict[str, str]],
    dict[str, int],
]:
    raw_samples: dict[str, list[float]] = {name: [] for name in task_names}
    mcp_samples: dict[str, list[float]] = {name: [] for name in task_names}
    failures: dict[str, dict[str, str]] = {}
    sizes: dict[str, int] = {}

    for round_index in range(-warmup, iterations):
        for name in task_names:
            # Alternate which group runs first each round to cancel drift.
            groups = ("raw", "mcp") if round_index % 2 == 0 else ("mcp", "raw")
            for group in groups:
                if group == "mcp":
                    _clear_caches()
                    # Mirror production _run_tool(): activate the request context
                    # so observability and upstream jitter engage the same way.
                    begin_request(uuid.uuid4().hex)
                started = time.perf_counter()
                try:
                    result = await tasks[name][group]()
                    elapsed = (time.perf_counter() - started) * 1000
                    if round_index >= 0:
                        (raw_samples if group == "raw" else mcp_samples)[name].append(
                            elapsed
                        )
                    if name not in sizes:
                        try:
                            sizes[name] = len(
                                json.dumps(result, ensure_ascii=False, default=str)
                            )
                        except Exception:
                            sizes[name] = -1
                except Exception as exc:
                    if round_index >= 0:
                        failures.setdefault(name, {})[
                            group
                        ] = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(gap)

    return raw_samples, mcp_samples, failures, sizes


async def _measure_warm_cache(uid: int, cred, iterations: int) -> dict[str, float]:
    """user_info with a hot async-lru cache (no upstream work)."""
    await core.fetch_user_info(uid, cred)  # prime
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        await core.fetch_user_info(uid, cred)
        samples.append((time.perf_counter() - started) * 1000)
    return _stats(samples)


async def _measure_mcp_protocol(uid: int, iterations: int) -> dict[str, float]:
    """In-memory FastMCP client round-trip on a hot cache (protocol overhead)."""
    from fastmcp import Client

    from bili_stalker_mcp.server import create_server

    mcp = create_server()
    async with Client(mcp) as client:
        await client.call_tool("get_user_info", {"user_id_or_username": str(uid)})
        samples: list[float] = []
        for _ in range(iterations):
            started = time.perf_counter()
            await client.call_tool("get_user_info", {"user_id_or_username": str(uid)})
            samples.append((time.perf_counter() - started) * 1000)
    return _stats(samples)


async def main() -> None:
    args = _parse_args()
    uid = int(args.user)

    if load_dotenv is not None:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not os.environ.get("BUVID3") and os.environ.get("BUVID"):
        os.environ["BUVID3"] = os.environ["BUVID"]

    cred = core.get_credential()
    if cred is None:
        raise RuntimeError("Missing SESSDATA credential")

    task_names = [t.strip() for t in args.tasks.split(",") if t.strip()]
    tasks = await _build_tasks(uid, args.limit, cred)

    # Warmup interleaves with measurement via negative round indices.
    raw_samples, mcp_samples, failures, sizes = await _run_benchmark(
        tasks, task_names, args.iterations, warmup=1, gap=args.gap
    )

    results: dict[str, object] = {}
    for name in task_names:
        raw_stats = _stats(raw_samples[name])
        mcp_stats = _stats(mcp_samples[name])
        entry: dict[str, object] = {
            "raw": raw_stats,
            "mcp_cold": mcp_stats,
            "result_bytes": sizes.get(name),
        }
        if raw_stats.get("count") and mcp_stats.get("count"):
            entry["overhead_ms"] = round(
                float(mcp_stats["avg_ms"]) - float(raw_stats["avg_ms"]), 1
            )
            entry["overhead_ratio"] = round(
                float(mcp_stats["avg_ms"]) / float(raw_stats["avg_ms"]), 3
            )
        if name in failures and "raw" in failures[name]:
            entry["raw_failures"] = failures[name]["raw"]
        if name in failures and "mcp" in failures[name]:
            entry["mcp_failures"] = failures[name]["mcp"]
        results[name] = entry

    _clear_caches()
    warm = await _measure_warm_cache(uid, cred, iterations=args.iterations)
    protocol = await _measure_mcp_protocol(uid, iterations=10)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uid": uid,
        "iterations": args.iterations,
        "limit": args.limit,
        "gap_seconds": args.gap,
        "pacing": (
            "default" if os.environ.get("BILI_PERF_KEEP_PACING") == "1" else "disabled"
        ),
        "proxy": BENCH_PROXY or None,
        "tasks": results,
        "warm_cache_user_info": warm,
        "mcp_protocol_hot_user_info": protocol,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
