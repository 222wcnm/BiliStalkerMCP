import argparse
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Awaitable, Callable

from bili_stalker_mcp import core
from bili_stalker_mcp.observability import begin_request, snapshot_metrics


ToolRunner = Callable[[int, int, Any], Awaitable[dict[str, Any]]]


@dataclass
class Sample:
    duration_ms: float
    upstream_duration_ms: float
    retry_count: int
    cache: dict[str, dict[str, float | int]]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run lightweight performance baseline for BiliStalkerMCP tools.")
    parser.add_argument("-u", "--user", required=True, help="UID or username")
    parser.add_argument("-n", "--iterations", type=int, default=3, help="iterations per tool (default: 3)")
    parser.add_argument("-l", "--limit", type=int, default=10, help="limit/page size for list tools (default: 10)")
    parser.add_argument(
        "--tools",
        default="videos,dynamics",
        help="comma-separated tools: user_info,videos,dynamics,articles,followings (default: videos,dynamics)",
    )
    parser.add_argument("--warmup", type=int, default=1, help="warmup runs per tool (default: 1)")
    return parser.parse_args()


def _available_tools() -> dict[str, ToolRunner]:
    return {
        "user_info": lambda uid, limit, cred: core.fetch_user_info(uid, cred),
        "videos": lambda uid, limit, cred: core.fetch_user_videos(uid, 1, limit, cred),
        "dynamics": lambda uid, limit, cred: core.fetch_user_dynamics(uid, 0, limit, cred, "ALL"),
        "articles": lambda uid, limit, cred: core.fetch_user_articles(uid, 1, limit, cred),
        "followings": lambda uid, limit, cred: core.fetch_user_followings(uid, 1, limit, cred),
    }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = int(round((len(sorted_values) - 1) * p))
    return float(sorted_values[k])


def _merge_cache(samples: list[Sample]) -> dict[str, dict[str, float | int]]:
    merged: dict[str, dict[str, float | int]] = {}
    for sample in samples:
        for cache_name, item in sample.cache.items():
            stats = merged.setdefault(cache_name, {"hit": 0, "miss": 0, "total": 0, "hit_rate": 0.0})
            stats["hit"] = int(stats["hit"]) + int(item.get("hit", 0))
            stats["miss"] = int(stats["miss"]) + int(item.get("miss", 0))

    for cache_name, stats in merged.items():
        total = int(stats["hit"]) + int(stats["miss"])
        stats["total"] = total
        stats["hit_rate"] = round((int(stats["hit"]) / total) if total > 0 else 0.0, 4)
        merged[cache_name] = stats

    return merged


async def _resolve_uid(user_input: str) -> int:
    if user_input.isdigit():
        return int(user_input)

    uid = await core.get_user_id_by_username(user_input)
    if uid is None:
        raise RuntimeError(f"User '{user_input}' not found")
    return uid


async def _run_once(tool_name: str, runner: ToolRunner, uid: int, limit: int, cred: Any) -> Sample:
    begin_request(uuid.uuid4().hex)
    started = time.perf_counter()
    await runner(uid, limit, cred)
    duration_ms = (time.perf_counter() - started) * 1000
    metrics = snapshot_metrics()

    return Sample(
        duration_ms=duration_ms,
        upstream_duration_ms=float(metrics.get("upstream_duration_ms", 0.0)),
        retry_count=int(metrics.get("retry_count", 0)),
        cache=metrics.get("cache", {}),
    )


async def _benchmark_tool(
    tool_name: str,
    runner: ToolRunner,
    uid: int,
    limit: int,
    cred: Any,
    iterations: int,
    warmup: int,
) -> dict[str, Any]:
    for _ in range(max(0, warmup)):
        try:
            await _run_once(tool_name, runner, uid, limit, cred)
        except Exception:
            pass

    samples: list[Sample] = []
    failures = 0
    failure_examples: list[str] = []

    for _ in range(iterations):
        try:
            sample = await _run_once(tool_name, runner, uid, limit, cred)
            samples.append(sample)
        except Exception as exc:
            failures += 1
            if len(failure_examples) < 3:
                failure_examples.append(str(exc))

    durations = [s.duration_ms for s in samples]
    upstreams = [s.upstream_duration_ms for s in samples]
    retries = [s.retry_count for s in samples]

    return {
        "iterations": iterations,
        "success_count": len(samples),
        "failure_count": failures,
        "failure_examples": failure_examples,
        "avg_duration_ms": round(mean(durations), 3) if durations else None,
        "p95_duration_ms": round(_percentile(durations, 0.95), 3) if durations else None,
        "avg_upstream_duration_ms": round(mean(upstreams), 3) if upstreams else None,
        "avg_retry_count": round(mean(retries), 3) if retries else None,
        "cache": _merge_cache(samples),
    }


async def main() -> None:
    args = _parse_args()

    if args.iterations <= 0:
        raise RuntimeError("iterations must be > 0")
    if args.limit <= 0:
        raise RuntimeError("limit must be > 0")

    cred = core.get_credential()
    if cred is None:
        raise RuntimeError("Missing SESSDATA in environment")

    uid = await _resolve_uid(args.user)

    available = _available_tools()
    selected_tools = [item.strip() for item in args.tools.split(",") if item.strip()]
    invalid = [name for name in selected_tools if name not in available]
    if invalid:
        valid = ", ".join(sorted(available))
        raise RuntimeError(f"Unknown tools: {', '.join(invalid)}. Valid tools: {valid}")

    results: dict[str, Any] = {}
    for tool_name in selected_tools:
        results[tool_name] = await _benchmark_tool(
            tool_name=tool_name,
            runner=available[tool_name],
            uid=uid,
            limit=args.limit,
            cred=cred,
            iterations=args.iterations,
            warmup=args.warmup,
        )

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": args.user,
        "uid": uid,
        "iterations": args.iterations,
        "limit": args.limit,
        "tools": selected_tools,
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
