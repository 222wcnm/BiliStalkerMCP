import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from async_lru import alru_cache

from bili_stalker_mcp.deadline import (
    deadline_scope,
    wait_cached,
    without_request_deadline,
)
from bili_stalker_mcp.errors import ToolTimeoutError
from bili_stalker_mcp.infra import upstream
from bili_stalker_mcp.infra.circuit_breaker import reset_risk_control_circuit
from bili_stalker_mcp.models import SubtitleResponse
from bili_stalker_mcp.observability import begin_request
from bili_stalker_mcp.services import dynamic_service, user_service
from bili_stalker_mcp.utils import video_id_parser


@pytest.fixture(autouse=True)
def isolated_cache_requests(monkeypatch):
    caches = (
        user_service._fetch_user_videos_cached,
        user_service._fetch_user_info_cached,
        user_service._fetch_video_metadata_cached,
        user_service._fetch_video_detail_cached,
        dynamic_service._fetch_user_dynamics_cached,
        video_id_parser._resolve_short_link_cached,
    )
    begin_request("cache-deadline-test")
    reset_risk_control_circuit()
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "never")
    for cache in caches:
        cache.cache_clear()
    yield
    for cache in caches:
        cache.cache_clear()
    reset_risk_control_circuit()


async def within_budget(seconds, function):
    async with deadline_scope(time.monotonic() + seconds):
        return await function()


def test_finished_worker_callback_does_not_starve_event_loop():
    state = {}

    async def exercise():
        completed = asyncio.Event()

        @alru_cache()
        @without_request_deadline
        async def cached():
            completed.set()
            return "complete"

        state["active"] = getattr(cached, "_cache_work")

        async def later():
            await completed.wait()
            return await wait_cached(cached)

        first = asyncio.create_task(wait_cached(cached))
        second = asyncio.create_task(later())
        state["results"] = await asyncio.gather(first, second)

    def run():
        try:
            asyncio.run(exercise())
        except BaseException as exc:
            state["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=2)
    stalled = thread.is_alive()
    if stalled:
        # Release a busy-loop regression so the test can fail without leaking a thread.
        state.get("active", {}).clear()
        thread.join(timeout=2)
    assert (
        not stalled
    ), "completed cache work prevented its cleanup callback from running"
    assert "error" not in state
    assert state["results"] == ["complete", "complete"]


@pytest.mark.asyncio
async def test_new_caller_waits_for_old_cancelled_worker_cleanup():
    cleaning = asyncio.Event()
    release = asyncio.Event()
    attempts = []

    @alru_cache()
    @without_request_deadline
    async def cached():
        attempts.append(1)
        if len(attempts) == 1:
            try:
                await asyncio.sleep(10)
            finally:
                cleaning.set()
                await release.wait()
        return "complete"

    async def function():
        return await wait_cached(cached)

    first = asyncio.create_task(within_budget(0.03, function))
    await asyncio.wait_for(cleaning.wait(), 1)
    second = asyncio.create_task(within_budget(0.8, function))
    await asyncio.sleep(0.01)
    assert len(attempts) == 1
    release.set()
    early, complete = await asyncio.gather(first, second, return_exceptions=True)
    assert isinstance(early, ToolTimeoutError)
    assert complete == "complete"
    assert await within_budget(0.8, function) == "complete"
    assert len(attempts) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["videos", "short_link"])
async def test_shared_work_keeps_each_callers_budget(monkeypatch, kind):
    started = asyncio.Event()
    attempts = []
    credential = object()

    async def request(*_args, **_kwargs):
        attempts.append(1)
        started.set()
        await asyncio.sleep(0.15)
        if kind == "videos":
            return {"list": {"vlist": []}, "page": {"count": 0}}
        return httpx.Response(
            302, headers={"Location": "https://www.bilibili.com/video/BV1xx411c7mD?p=2"}
        )

    if kind == "videos":
        monkeypatch.setattr(
            user_service.user, "User", lambda **_kw: SimpleNamespace(get_videos=request)
        )
    else:
        monkeypatch.setattr(
            video_id_parser,
            "get_shared_http_client",
            lambda: SimpleNamespace(head=request),
        )

    async def function():
        if kind == "videos":
            return await user_service.fetch_user_videos(123, 1, 5, credential)
        return await video_id_parser.extract_video_reference(
            "https://b23.tv/review-regression"
        )

    first = asyncio.create_task(within_budget(0.06, function))
    await asyncio.wait_for(started.wait(), 1)
    second = asyncio.create_task(within_budget(0.6, function))
    early, complete = await asyncio.gather(first, second, return_exceptions=True)
    assert isinstance(early, ToolTimeoutError)
    assert not isinstance(complete, BaseException)
    assert len(attempts) == 1
    assert await within_budget(0.6, function) == complete
    assert len(attempts) == 1
    if kind == "short_link":
        assert complete.page == 2


@pytest.mark.asyncio
async def test_cancelled_optional_stats_do_not_poison_user_cache(monkeypatch):
    credential = type("Credential", (), {"bili_jct": None})()
    info = AsyncMock(return_value={"mid": 123, "name": "demo"})
    monkeypatch.setattr(
        user_service.user, "User", lambda **_kw: SimpleNamespace(get_user_info=info)
    )
    attempts = []
    cancelled = asyncio.Event()

    async def relation(*_args, **_kwargs):
        attempts.append(1)
        try:
            return await upstream.timed_upstream_call(
                asyncio.sleep(
                    0.15, result={"code": 0, "data": {"following": 10, "follower": 999}}
                )
            )
        finally:
            cancelled.set()

    monkeypatch.setattr(user_service, "get_json", relation)

    async def function():
        return await user_service.fetch_user_info(123, credential)

    with pytest.raises(ToolTimeoutError):
        await within_budget(0.05, function)
    await asyncio.wait_for(cancelled.wait(), 1)
    await asyncio.sleep(0)
    assert user_service._fetch_user_info_cached.cache_info().currsize == 0
    result = await within_budget(0.6, function)
    assert result["follower"] == 999
    assert len(attempts) == 2
    assert await within_budget(0.6, function) == result
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_last_waiter_cancels_dynamic_lazy_pause(monkeypatch):
    credential = object()
    calls = []
    card = {
        "id_str": "1",
        "type": "DYNAMIC_TYPE_WORD",
        "modules": {
            "module_author": {"pub_ts": 1771601421},
            "module_dynamic": {"desc": {"text": "text"}, "major": None},
            "module_stat": {},
        },
    }

    async def page(offset):
        calls.append(offset)
        return {"items": [card], "has_more": True, "offset": "next"}

    monkeypatch.setattr(
        dynamic_service.user,
        "User",
        lambda **_kw: SimpleNamespace(get_dynamics_new=page),
    )
    monkeypatch.setattr(dynamic_service, "LAZY_ENABLED", True)
    monkeypatch.setattr(dynamic_service, "LAZY_DYNAMICS_BATCH", 1)
    monkeypatch.setattr(dynamic_service, "LAZY_SLEEP_MIN_SECONDS", 0.3)
    monkeypatch.setattr(dynamic_service, "LAZY_SLEEP_MAX_SECONDS", 0.3)

    async def function():
        return await dynamic_service.fetch_user_dynamics(123, 2, credential, "TEXT")

    with pytest.raises(ToolTimeoutError):
        await within_budget(0.04, function)
    await asyncio.sleep(0.02)
    assert dynamic_service._fetch_user_dynamics_cached.cache_parameters()["tasks"] == 0
    assert dynamic_service._fetch_user_dynamics_cached.cache_info().currsize == 0
    assert len(calls) == 1
    result = await within_budget(1, function)
    assert result["total_fetched"] == 2
    assert len(calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_first", [False, True])
async def test_partial_video_cannot_cancel_or_poison_other_waiter(
    monkeypatch, cancel_first
):
    started = asyncio.Event()
    attempts = []
    info = AsyncMock(
        return_value={
            "bvid": "BV1xx411c7mD",
            "title": "video metadata",
            "stat": {},
            "pages": [{"cid": 101, "page": 1, "part": "P1", "duration": 30}],
        }
    )
    monkeypatch.setattr(
        user_service.video, "Video", lambda **_kw: SimpleNamespace(get_info=info)
    )

    async def subtitles(*_args, **_kwargs):
        attempts.append(1)
        started.set()
        await asyncio.sleep(0.25)
        return SubtitleResponse(mode="smart", returned_chars=4, full_text="text")

    monkeypatch.setattr(user_service, "collect_subtitles", subtitles)

    async def function():
        return await user_service.fetch_video_detail("BV1xx411c7mD", True)

    first = asyncio.create_task(within_budget(0.3, function))
    await asyncio.wait_for(started.wait(), 1)
    second = asyncio.create_task(within_budget(0.8, function))
    if cancel_first:
        await asyncio.sleep(0.02)
        first.cancel()
    partial, complete = await asyncio.gather(first, second, return_exceptions=True)
    if cancel_first:
        assert isinstance(partial, asyncio.CancelledError)
    else:
        assert partial["video"]["title"] == "video metadata"
        assert partial["subtitles"]["errors"] == [user_service.SUBTITLE_TIMEOUT_REASON]
    assert complete["subtitles"]["full_text"] == "text"
    assert not complete["subtitles"]["errors"]
    assert len(attempts) == 1 and info.await_count == 1
    assert await within_budget(0.8, function) == complete
    assert len(attempts) == 1 and info.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [0.05, 0.8])
async def test_complete_video_cache_does_not_require_metadata_cache(
    monkeypatch, budget
):
    info = AsyncMock(
        return_value={
            "bvid": "BV1xx411c7mD",
            "title": "cached metadata",
            "stat": {},
            "pages": [{"cid": 101, "page": 1, "part": "P1", "duration": 30}],
        }
    )
    monkeypatch.setattr(
        user_service.video, "Video", lambda **_kw: SimpleNamespace(get_info=info)
    )
    subtitles = AsyncMock(
        return_value=SubtitleResponse(mode="smart", returned_chars=4, full_text="text")
    )
    monkeypatch.setattr(user_service, "collect_subtitles", subtitles)

    async def function():
        return await user_service.fetch_video_detail("BV1xx411c7mD", True)

    complete = await within_budget(0.8, function)
    user_service._fetch_video_metadata_cached.cache_clear()
    info.side_effect = RuntimeError("metadata upstream unavailable")
    assert await within_budget(budget, function) == complete
    assert info.await_count == 1
    assert subtitles.await_count == 1
    assert user_service._fetch_video_detail_cached.cache_info().hits == 1
