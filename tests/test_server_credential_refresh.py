import asyncio
import json

import pytest
from bilibili_api import Credential
from fastmcp.exceptions import ToolError

from bili_stalker_mcp import core
from bili_stalker_mcp import server as server_module
from bili_stalker_mcp.cookie_refresh import (
    CookieRefreshConfigError,
    CookieRefreshCoordinator,
)
from bili_stalker_mcp.errors import RiskControlError, public_error_json

COOKIE_ENV_NAMES = (
    "SESSDATA",
    "BILI_JCT",
    "BUVID3",
    "BUVID4",
    "DEDEUSERID",
    "BILI_COOKIE_FILE",
    "BILI_REFRESH_TOKEN_FILE",
    "BILI_ENABLE_COOKIE_REFRESH",
    "BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS",
)


@pytest.mark.asyncio
async def test_credential_entrypoint_returns_refreshed_credential(monkeypatch):
    new_credential = Credential(sessdata="new_sessdata")

    monkeypatch.setattr(server_module, "cookie_refresh_enabled", lambda: True)
    monkeypatch.setattr(
        server_module,
        "get_credential",
        lambda: pytest.fail("refreshing path must load inside the coordinator"),
    )

    async def fake_load_refreshing_credential():
        return new_credential

    monkeypatch.setattr(
        server_module,
        "load_refreshing_credential",
        fake_load_refreshing_credential,
    )

    result = await server_module._get_credential_from_context(object())

    assert result is new_credential


@pytest.mark.asyncio
async def test_credential_entrypoint_preserves_safe_refresh_config_error(monkeypatch):
    monkeypatch.setattr(server_module, "cookie_refresh_enabled", lambda: True)

    async def fake_load_refreshing_credential():
        raise CookieRefreshConfigError("BILI_COOKIE_FILE", "SESSDATA")

    monkeypatch.setattr(
        server_module,
        "load_refreshing_credential",
        fake_load_refreshing_credential,
    )

    with pytest.raises(ToolError) as exc_info:
        await server_module._get_credential_from_context(object())

    error_text = str(exc_info.value)
    assert "BILI_COOKIE_FILE" in error_text
    assert "SESSDATA" in error_text
    assert "private_sessdata" not in error_text


@pytest.mark.asyncio
async def test_credential_entrypoint_preserves_structured_risk_control(monkeypatch):
    monkeypatch.setattr(server_module, "cookie_refresh_enabled", lambda: True)

    async def fake_load_refreshing_credential():
        raise RiskControlError(retry_after=9)

    monkeypatch.setattr(
        server_module,
        "load_refreshing_credential",
        fake_load_refreshing_credential,
    )

    with pytest.raises(ToolError) as exc_info:
        await server_module._get_credential_from_context(object())

    payload = json.loads(str(exc_info.value))
    assert payload["code"] == 412
    assert payload["reason"] == "risk_control"
    assert payload["retry_after"] == 9

    normalized = json.loads(public_error_json(exc_info.value, request_id="test-id"))
    assert normalized["reason"] == "risk_control"
    assert normalized["retry_after"] == 9
    assert normalized["request_id"] == "test-id"


@pytest.mark.asyncio
async def test_credential_entrypoint_redacts_unexpected_refresh_errors(monkeypatch):
    secret = "unexpected_refresh_secret"
    monkeypatch.setattr(server_module, "cookie_refresh_enabled", lambda: True)

    async def fake_load_refreshing_credential():
        raise RuntimeError(secret)

    monkeypatch.setattr(
        server_module,
        "load_refreshing_credential",
        fake_load_refreshing_credential,
    )

    with pytest.raises(ToolError) as exc_info:
        await server_module._get_credential_from_context(object())

    error_text = str(exc_info.value)
    assert secret not in error_text
    assert json.loads(error_text)["reason"] == "internal_error"


@pytest.mark.asyncio
async def test_credential_entrypoint_reports_enabled_preflight_errors_safely(
    monkeypatch,
):
    secret = "configured_but_private_sessdata"
    for name in COOKIE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SESSDATA", secret)
    monkeypatch.setattr(server_module, "cookie_refresh_enabled", lambda: True)

    async def fake_load_refreshing_credential():
        raise CookieRefreshConfigError("BILI_COOKIE_FILE", "BILI_REFRESH_TOKEN_FILE")

    monkeypatch.setattr(
        server_module,
        "load_refreshing_credential",
        fake_load_refreshing_credential,
    )

    with pytest.raises(ToolError) as exc_info:
        await server_module._get_credential_from_context(object())

    error_text = str(exc_info.value)
    assert "BILI_COOKIE_FILE" in error_text
    assert "BILI_REFRESH_TOKEN_FILE" in error_text
    assert secret not in error_text


@pytest.mark.asyncio
async def test_disabled_refresh_uses_synchronous_credential_loader(monkeypatch):
    credential = Credential(sessdata="test_sessdata")
    monkeypatch.setattr(server_module, "cookie_refresh_enabled", lambda: False)
    monkeypatch.setattr(server_module, "get_credential", lambda: credential)

    async def unexpected_refresh_load():
        pytest.fail("disabled refresh must not inspect refresh files")

    monkeypatch.setattr(
        server_module, "load_refreshing_credential", unexpected_refresh_load
    )

    assert await server_module._get_credential_from_context(object()) is credential


@pytest.mark.asyncio
async def test_all_public_tools_await_unified_credential_entrypoint(monkeypatch):
    marker = "credential_entrypoint_reached"
    calls = 0

    async def stop_at_credential_entrypoint(_ctx):
        nonlocal calls
        calls += 1
        raise ToolError(marker)

    async def fail_on_upstream(*_args, **_kwargs):
        raise AssertionError("upstream reached before credential entrypoint")

    monkeypatch.setattr(
        server_module,
        "_get_credential_from_context",
        stop_at_credential_entrypoint,
    )
    for name in (
        "fetch_user_info",
        "fetch_user_videos",
        "fetch_video_detail",
        "fetch_user_dynamics",
        "fetch_user_articles",
        "fetch_article_content",
        "fetch_user_followings",
        "fetch_content_comments",
        "fetch_content_comment_replies",
    ):
        monkeypatch.setattr(server_module, name, fail_on_upstream)

    tool_arguments = {
        "get_user_info": {"user_id_or_username": "1"},
        "get_user_videos": {"user_id_or_username": "1"},
        "search_user_videos": {
            "user_id_or_username": "1",
            "keyword": "test",
        },
        "get_video_detail": {"bvid": "BV1xx411c7mD"},
        "get_user_dynamics": {"user_id_or_username": "1"},
        "get_user_articles": {"user_id_or_username": "1"},
        "get_article_content": {"article_id": "1"},
        "get_user_followings": {"user_id_or_username": "1"},
        "get_content_comments": {
            "content_type": "article",
            "content_id": "1",
        },
        "get_content_comment_replies": {
            "content_type": "article",
            "content_id": "1",
            "root_rpid": 1,
        },
    }
    tools = {
        tool.name: tool for tool in await server_module.create_server().list_tools()
    }

    for expected_calls, (tool_name, arguments) in enumerate(
        tool_arguments.items(),
        start=1,
    ):
        with pytest.raises(ToolError, match=marker):
            await tools[tool_name].fn(ctx=object(), **arguments)
        assert calls == expected_calls


@pytest.mark.asyncio
async def test_concurrent_calls_wait_for_one_refresh_and_use_latest_credential(
    monkeypatch,
    tmp_path,
):
    for name in COOKIE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(core, "_credential_cache_key", None)
    monkeypatch.setattr(core, "_credential_cache_value", None)

    cookie_file = tmp_path / "cookie.txt"
    refresh_token_file = tmp_path / "refresh-token.txt"
    cookie_file.write_text(
        "SESSDATA=old_sessdata; bili_jct=old_jct; DedeUserID=1\n",
        encoding="utf-8",
    )
    refresh_token_file.write_text("old_refresh_token\n", encoding="utf-8")
    monkeypatch.setenv("BILI_ENABLE_COOKIE_REFRESH", "true")
    monkeypatch.setenv("BILI_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("BILI_REFRESH_TOKEN_FILE", str(refresh_token_file))
    monkeypatch.setenv("BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS", "60")

    old_credential = core.get_credential()
    assert old_credential is not None

    class FakeAdapter:
        def __init__(self):
            self.check_started = asyncio.Event()
            self.allow_check = asyncio.Event()
            self.check_calls = 0
            self.refresh_calls = 0
            self.confirm_calls = 0
            self.refreshed = Credential(
                sessdata="new_sessdata",
                bili_jct="new_jct",
                dedeuserid="2",
                ac_time_value="new_refresh_token",
            )

        async def check_refresh(self, credential):
            assert credential is old_credential
            self.check_calls += 1
            self.check_started.set()
            await self.allow_check.wait()
            return True

        async def refresh(self, credential):
            assert credential is old_credential
            self.refresh_calls += 1
            return self.refreshed

        async def confirm(self, old_refresh_token, credential):
            assert old_refresh_token == "old_refresh_token"
            assert credential is self.refreshed
            self.confirm_calls += 1

    adapter = FakeAdapter()
    coordinator = CookieRefreshCoordinator(adapter=adapter, clock=lambda: 100.0)
    first = asyncio.create_task(coordinator.maybe_refresh(old_credential))
    await asyncio.wait_for(adapter.check_started.wait(), timeout=1)
    waiters = [
        asyncio.create_task(coordinator.maybe_refresh(old_credential)) for _ in range(4)
    ]
    await asyncio.sleep(0)
    adapter.allow_check.set()

    results = await asyncio.gather(first, *waiters)

    assert adapter.check_calls == 1
    assert adapter.refresh_calls == 1
    assert adapter.confirm_calls == 1
    assert all(result.sessdata == "new_sessdata" for result in results)
    assert all(result.ac_time_value == "new_refresh_token" for result in results)

    next_credential = core.get_credential()
    assert next_credential is not None
    assert next_credential is not old_credential
    assert next_credential.get_cookies()["SESSDATA"] == "new_sessdata"
    assert next_credential.ac_time_value == "new_refresh_token"


def test_get_credential_replaces_cached_object_after_cookie_file_rotation(
    monkeypatch, tmp_path
):
    for name in COOKIE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(core, "_credential_cache_key", None)
    monkeypatch.setattr(core, "_credential_cache_value", None)

    cookie_file = tmp_path / "cookie.txt"
    cookie_file.write_text(
        "SESSDATA=old_sessdata; bili_jct=old_jct\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BILI_COOKIE_FILE", str(cookie_file))

    old_credential = core.get_credential()
    assert old_credential is not None

    cookie_file.write_text(
        "SESSDATA=new_sessdata; bili_jct=new_jct\n",
        encoding="utf-8",
    )
    new_credential = core.get_credential()

    assert new_credential is not None
    assert new_credential is not old_credential
    assert new_credential.get_cookies()["SESSDATA"] == "new_sessdata"
    assert new_credential.get_cookies()["bili_jct"] == "new_jct"
