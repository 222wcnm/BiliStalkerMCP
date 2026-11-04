import asyncio
import inspect
import json
import time
from unittest.mock import AsyncMock

import pytest
from async_lru import alru_cache

from bili_stalker_mcp import cli, config, server
from bili_stalker_mcp.deadline import (
    deadline_scope,
    get_deadline,
    without_request_deadline,
)
from bili_stalker_mcp.errors import ToolTimeoutError
from bili_stalker_mcp.infra.upstream import timed_upstream_call
from bili_stalker_mcp.models import SubtitleResponse
from bili_stalker_mcp.observability import begin_request, register_upstream_call
from bili_stalker_mcp.retry import RetryableBiliApiError, with_retry
from bili_stalker_mcp.services import user_service


@pytest.fixture(autouse=True)
def isolate_request_state(monkeypatch):
    begin_request("deadline-test")
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MODE", "never")


@pytest.mark.asyncio
async def test_native_tool_timeout_cancels_work_and_returns_safe_error(monkeypatch):
    cancelled = asyncio.Event()

    async def slow_search(*_args):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    monkeypatch.setattr(server, "TOOL_TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr(server, "search_users_service", slow_search)
    with pytest.raises(Exception) as caught:
        await server.create_server().call_tool(
            "search_users", {"keyword": "private-input"}
        )
    error = json.loads(str(caught.value))
    assert error["reason"] == "tool_timeout"
    assert error["tool"] == "search_users"
    assert error["request_id"]
    assert "private-input" not in str(caught.value)
    assert cancelled.is_set()
    assert get_deadline() is None


def test_cli_budget_includes_argument_loading_before_tool_body(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_configure_logging", lambda: None)
    monkeypatch.setattr(config, "TOOL_TIMEOUT_SECONDS", 0.01)
    service = AsyncMock()
    monkeypatch.setattr(server, "search_users_service", service)

    def slow_arguments(_args):
        time.sleep(0.03)
        return {"keyword": "demo"}

    monkeypatch.setattr(cli, "_read_arguments", slow_arguments)
    assert cli.main(["call", "search_users"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err)["error"]["reason"] == "tool_timeout"
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_upstream_does_not_keep_running_past_deadline():
    begin_request("deadline-cached-upstream")
    cancelled = asyncio.Event()

    async def slow_request():
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    @alru_cache()
    @without_request_deadline
    async def cached():
        return await timed_upstream_call(slow_request())

    with pytest.raises(ToolTimeoutError):
        async with deadline_scope(time.monotonic() + 0.03):
            await cached()
    await asyncio.wait_for(cancelled.wait(), timeout=0.1)
    await asyncio.sleep(0)
    assert cached.cache_info().currsize == 0


@pytest.mark.asyncio
async def test_deadline_during_jitter_closes_unstarted_request(monkeypatch):
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MODE", "always")
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MIN_MS", 1000)
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MAX_MS", 1000)
    monkeypatch.setattr(
        "bili_stalker_mcp.infra.upstream.REQUEST_JITTER_BUDGET_MS", 1000
    )
    begin_request("deadline-during-jitter")
    register_upstream_call()
    started = []

    async def request():
        started.append(True)

    pending = request()
    with pytest.raises(ToolTimeoutError):
        async with deadline_scope(time.monotonic() + 0.02):
            await timed_upstream_call(pending)
    assert not started
    assert inspect.getcoroutinestate(pending) == inspect.CORO_CLOSED


@pytest.mark.asyncio
async def test_retry_backoff_stops_at_request_deadline():
    attempts = []

    @with_retry(max_retries=3, base_delay=5)
    async def rate_limited():
        attempts.append(1)
        raise RetryableBiliApiError(-509, "limited")

    with pytest.raises(ToolTimeoutError):
        async with deadline_scope(time.monotonic() + 0.03):
            await rate_limited()
    assert len(attempts) == 1
    assert get_deadline() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_caller", [False, True])
async def test_subtitle_deadline_preserves_video_without_caching_timeout(
    monkeypatch, cancel_caller
):
    user_service._fetch_video_detail_cached.cache_clear()
    user_service._fetch_video_metadata_cached.cache_clear()
    info = AsyncMock(
        return_value={
            "bvid": "BV1xx411c7mD",
            "title": "video metadata",
            "stat": {},
            "pages": [{"cid": 101, "page": 1, "part": "P1", "duration": 30}],
        }
    )

    class Video:
        get_info = info

    attempts = []
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def subtitles(*_args, **_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        return SubtitleResponse(mode="smart", returned_chars=4, full_text="text")

    monkeypatch.setattr(user_service.video, "Video", lambda **_kwargs: Video())
    monkeypatch.setattr(user_service, "collect_subtitles", subtitles)

    async def request():
        async with deadline_scope(time.monotonic() + 0.25):
            return await user_service.fetch_video_detail("BV1xx411c7mD", True)

    try:
        task = asyncio.create_task(request())
        if cancel_caller:
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(cancelled.wait(), timeout=1)
            await asyncio.sleep(0)
        else:
            partial = await task
            assert partial["video"]["title"] == "video metadata"
            assert partial["subtitles"]["errors"] == [
                user_service.SUBTITLE_TIMEOUT_REASON
            ]
        assert user_service._fetch_video_detail_cached.cache_info().currsize == 0
        async with deadline_scope(time.monotonic() + 1):
            complete = await user_service.fetch_video_detail("BV1xx411c7mD", True)
        assert complete["subtitles"]["full_text"] == "text"
        assert not complete["subtitles"]["errors"]
        assert info.await_count == 1
    finally:
        user_service._fetch_video_detail_cached.cache_clear()
        user_service._fetch_video_metadata_cached.cache_clear()


@pytest.mark.asyncio
async def test_caller_cancellation_is_not_converted_to_tool_timeout():
    started = asyncio.Event()

    async def work():
        async with deadline_scope(time.monotonic() + 10):
            started.set()
            await asyncio.sleep(10)

    task = asyncio.create_task(work())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_invalid_timeout_settings_use_safe_default(monkeypatch, value):
    monkeypatch.setenv("BILI_TOOL_TIMEOUT_SECONDS", value)
    assert config._positive_timeout("BILI_TOOL_TIMEOUT_SECONDS", 25) == 25
