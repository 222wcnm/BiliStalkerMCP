import asyncio
import copy
import logging
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from bilibili_api import Credential
from filelock import FileLock

from bili_stalker_mcp import cookie_refresh, credentials
from bili_stalker_mcp.cookie_refresh import (
    CookieRefreshConfigError,
    CookieRefreshCoordinator,
    CookieRefreshError,
)
from bili_stalker_mcp.errors import RiskControlError

OLD_SESSDATA = "test-old-sessdata"
OLD_CSRF = "test-old-csrf"
OLD_REFRESH_TOKEN = "test-old-refresh-token"
NEW_SESSDATA = "test-new-sessdata"
NEW_CSRF = "test-new-csrf"
NEW_REFRESH_TOKEN = "test-new-refresh-token"


def _credential(*, refreshed: bool = False) -> Credential:
    return Credential(
        sessdata=NEW_SESSDATA if refreshed else OLD_SESSDATA,
        bili_jct=NEW_CSRF if refreshed else OLD_CSRF,
        buvid3="test-buvid3",
        buvid4="test-buvid4",
        dedeuserid="test-user-id",
        ac_time_value=NEW_REFRESH_TOKEN if refreshed else OLD_REFRESH_TOKEN,
    )


def _enabled_env(tmp_path: Path) -> dict[str, str]:
    return {
        "BILI_ENABLE_COOKIE_REFRESH": "true",
        "BILI_COOKIE_FILE": str(tmp_path / "cookies.txt"),
        "BILI_REFRESH_TOKEN_FILE": str(tmp_path / "refresh-token.txt"),
    }


@dataclass
class _PersistenceState:
    files: credentials.CookieRefreshFiles
    pending: credentials.PendingConfirmation | None = None
    persist_calls: int = 0
    remove_calls: int = 0
    persisted_cookies: dict[str, str] | None = None


def _install_persistence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    pending: credentials.PendingConfirmation | None = None,
) -> _PersistenceState:
    state = _PersistenceState(
        files=credentials.CookieRefreshFiles(
            cookie_path=tmp_path / "cookies.txt",
            refresh_token_path=tmp_path / "refresh-token.txt",
        ),
        pending=pending,
    )
    credentials.write_cookie_file(
        state.files.cookie_path,
        {
            "sessdata": NEW_SESSDATA if pending is not None else OLD_SESSDATA,
            "bili_jct": NEW_CSRF if pending is not None else OLD_CSRF,
            "buvid3": "test-buvid3",
            "buvid4": "test-buvid4",
            "dedeuserid": "test-user-id",
        },
    )
    credentials.write_refresh_token_file(
        state.files.refresh_token_path,
        NEW_REFRESH_TOKEN if pending is not None else OLD_REFRESH_TOKEN,
    )
    monkeypatch.setattr(
        credentials,
        "read_pending_confirmation",
        lambda _path: state.pending,
        raising=False,
    )

    def persist(
        _cookie_path: Path,
        _token_path: Path,
        cookies: dict[str, str],
        new_token: str,
        old_token: str,
    ) -> None:
        state.persist_calls += 1
        state.persisted_cookies = dict(cookies)
        state.pending = credentials.PendingConfirmation(
            old_refresh_token=old_token,
            new_refresh_token=new_token,
        )

    def remove(_token_path: Path) -> None:
        state.remove_calls += 1
        state.pending = None

    monkeypatch.setattr(
        credentials, "persist_refreshed_credentials", persist, raising=False
    )
    monkeypatch.setattr(
        credentials, "remove_pending_confirmation", remove, raising=False
    )
    return state


class _FakeAdapter:
    def __init__(self, *, check_result: bool = False) -> None:
        self.check_result = check_result
        self.check_calls = 0
        self.refresh_calls = 0
        self.confirm_calls = 0
        self.check_error: Exception | None = None
        self.refresh_error: Exception | None = None
        self.confirm_error: Exception | None = None
        self.check_started: asyncio.Event | None = None
        self.release_check: asyncio.Event | None = None

    async def check_refresh(self, _credential: Credential) -> bool:
        self.check_calls += 1
        if self.check_started is not None:
            self.check_started.set()
        if self.release_check is not None:
            await self.release_check.wait()
        if self.check_error is not None:
            raise self.check_error
        return self.check_result

    async def refresh(self, _credential: Credential) -> Credential:
        self.refresh_calls += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        return _credential_factory(refreshed=True)

    async def confirm(self, _old_refresh_token: str, _credential: Credential) -> None:
        self.confirm_calls += 1
        if self.confirm_error is not None:
            raise self.confirm_error


# Kept separate so test monkeypatch tracebacks never repr a Credential containing secrets.
_credential_factory = _credential


@pytest.mark.asyncio
async def test_default_disabled_does_no_io_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeAdapter(check_result=True)
    coordinator = CookieRefreshCoordinator(adapter=adapter)
    monkeypatch.setattr(
        credentials,
        "resolve_cookie_refresh_files",
        lambda _env: pytest.fail("disabled refresh must not inspect files"),
        raising=False,
    )

    original = _credential()
    result = await coordinator.maybe_refresh(original, env={})

    assert result is original
    assert adapter.check_calls == 0
    assert adapter.refresh_calls == 0


@pytest.mark.asyncio
async def test_interval_skip_and_false_check_do_not_refresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = _install_persistence(monkeypatch, tmp_path)
    adapter = _FakeAdapter(check_result=False)
    now = [0.0]
    coordinator = CookieRefreshCoordinator(adapter=adapter, clock=lambda: now[0])
    env = _enabled_env(tmp_path)
    env["BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS"] = "60"
    original = _credential()

    assert await coordinator.maybe_refresh(original, env=env) is original
    now[0] = 59.0
    assert await coordinator.maybe_refresh(original, env=env) is original

    assert adapter.check_calls == 1
    assert adapter.refresh_calls == 0
    assert state.persist_calls == 0


@pytest.mark.asyncio
async def test_concurrent_waiters_wait_and_receive_one_refreshed_credential(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = _install_persistence(monkeypatch, tmp_path)
    adapter = _FakeAdapter(check_result=True)
    adapter.check_started = asyncio.Event()
    adapter.release_check = asyncio.Event()
    coordinator = CookieRefreshCoordinator(adapter=adapter, clock=lambda: 10.0)
    env = _enabled_env(tmp_path)
    original = _credential()

    tasks = [
        asyncio.create_task(coordinator.maybe_refresh(original, env=env))
        for _ in range(5)
    ]
    await adapter.check_started.wait()
    await asyncio.sleep(0)

    assert all(not task.done() for task in tasks)
    adapter.release_check.set()
    results = await asyncio.gather(*tasks)

    assert adapter.check_calls == 1
    assert adapter.refresh_calls == 1
    assert adapter.confirm_calls == 1
    assert state.persist_calls == 1
    assert state.remove_calls == 1
    assert all(result is results[0] for result in results)
    assert results[0].sessdata == NEW_SESSDATA
    assert results[0].ac_time_value == NEW_REFRESH_TOKEN
    assert "refresh_token" not in (state.persisted_cookies or {})
    assert "ac_time_value" not in (state.persisted_cookies or {})


@pytest.mark.asyncio
async def test_independent_coordinators_share_file_lock_and_reload(
    tmp_path: Path,
) -> None:
    files = credentials.CookieRefreshFiles(
        cookie_path=tmp_path / "cookies.txt",
        refresh_token_path=tmp_path / "refresh-token.txt",
    )
    credentials.write_cookie_file(
        files.cookie_path,
        {
            "sessdata": OLD_SESSDATA,
            "bili_jct": OLD_CSRF,
            "buvid3": "test-buvid3",
            "buvid4": "test-buvid4",
            "dedeuserid": "test-user-id",
        },
    )
    credentials.write_refresh_token_file(files.refresh_token_path, OLD_REFRESH_TOKEN)
    env = _enabled_env(tmp_path)
    first_adapter = _FakeAdapter(check_result=True)
    first_adapter.check_started = asyncio.Event()
    first_adapter.release_check = asyncio.Event()
    second_adapter = _FakeAdapter(check_result=True)
    first_coordinator = CookieRefreshCoordinator(adapter=first_adapter)
    second_coordinator = CookieRefreshCoordinator(adapter=second_adapter)

    first_task = asyncio.create_task(first_coordinator.load_and_maybe_refresh(env=env))
    await asyncio.wait_for(first_adapter.check_started.wait(), timeout=2)
    second_task = asyncio.create_task(
        second_coordinator.load_and_maybe_refresh(env=env)
    )
    await asyncio.sleep(0.05)
    assert not second_task.done()

    first_adapter.release_check.set()
    first_result, second_result = await asyncio.gather(first_task, second_task)

    assert first_adapter.refresh_calls == 1
    assert second_adapter.check_calls == 0
    assert first_result.sessdata == NEW_SESSDATA
    assert second_result.sessdata == NEW_SESSDATA
    assert second_result.ac_time_value == NEW_REFRESH_TOKEN


@pytest.mark.asyncio
async def test_file_lock_timeout_is_public_safe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_persistence(monkeypatch, tmp_path)
    env = _enabled_env(tmp_path)
    files = credentials.resolve_cookie_refresh_file_paths(env)
    monkeypatch.setattr(credentials, "COOKIE_REFRESH_LOCK_TIMEOUT_SECONDS", 0.05)
    coordinator = CookieRefreshCoordinator(adapter=_FakeAdapter())

    with FileLock(str(files.lock_path)):
        with pytest.raises(CookieRefreshError) as exc_info:
            await coordinator.load_and_maybe_refresh(env=env)

    message = str(exc_info.value)
    assert "Timed out" in message
    assert str(tmp_path) not in message
    assert OLD_SESSDATA not in message
    assert OLD_REFRESH_TOKEN not in message


@pytest.mark.asyncio
async def test_check_failure_is_rate_limited_and_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _install_persistence(monkeypatch, tmp_path)
    adapter = _FakeAdapter()
    adapter.check_error = RuntimeError(
        f"response {OLD_SESSDATA} {OLD_CSRF} {OLD_REFRESH_TOKEN}"
    )
    coordinator = CookieRefreshCoordinator(adapter=adapter, clock=lambda: 0.0)
    env = _enabled_env(tmp_path)
    original = _credential()

    with caplog.at_level(logging.WARNING):
        first = await coordinator.maybe_refresh(original, env=env)
        second = await coordinator.maybe_refresh(original, env=env)

    assert first is original
    assert second is original
    assert adapter.check_calls == 1
    assert adapter.refresh_calls == 0
    assert OLD_SESSDATA not in caplog.text
    assert OLD_CSRF not in caplog.text
    assert OLD_REFRESH_TOKEN not in caplog.text


@pytest.mark.asyncio
async def test_refresh_failure_is_not_retried_or_persisted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = _install_persistence(monkeypatch, tmp_path)
    adapter = _FakeAdapter(check_result=True)
    adapter.refresh_error = RuntimeError(f"failed with {OLD_REFRESH_TOKEN}")
    coordinator = CookieRefreshCoordinator(adapter=adapter)

    with pytest.raises(CookieRefreshError) as exc_info:
        await coordinator.maybe_refresh(_credential(), env=_enabled_env(tmp_path))

    assert adapter.check_calls == 1
    assert adapter.refresh_calls == 1
    assert adapter.confirm_calls == 0
    assert state.persist_calls == 0
    assert OLD_REFRESH_TOKEN not in str(exc_info.value)


@pytest.mark.asyncio
async def test_pending_confirmation_failure_prevents_another_refresh_and_is_limited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pending = credentials.PendingConfirmation(
        old_refresh_token=OLD_REFRESH_TOKEN,
        new_refresh_token=NEW_REFRESH_TOKEN,
    )
    state = _install_persistence(monkeypatch, tmp_path, pending=pending)
    adapter = _FakeAdapter(check_result=True)
    adapter.confirm_error = RuntimeError("confirm failed")
    coordinator = CookieRefreshCoordinator(adapter=adapter, clock=lambda: 0.0)
    current = _credential(refreshed=True)
    env = _enabled_env(tmp_path)

    assert await coordinator.maybe_refresh(current, env=env) is current
    assert await coordinator.maybe_refresh(current, env=env) is current

    assert adapter.confirm_calls == 1
    assert adapter.check_calls == 0
    assert adapter.refresh_calls == 0
    assert state.pending is pending
    assert state.remove_calls == 0


@pytest.mark.asyncio
async def test_pending_confirmation_success_removes_state_before_any_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pending = credentials.PendingConfirmation(
        old_refresh_token=OLD_REFRESH_TOKEN,
        new_refresh_token=NEW_REFRESH_TOKEN,
    )
    state = _install_persistence(monkeypatch, tmp_path, pending=pending)
    adapter = _FakeAdapter(check_result=True)
    coordinator = CookieRefreshCoordinator(adapter=adapter)
    current = _credential(refreshed=True)

    assert (
        await coordinator.maybe_refresh(current, env=_enabled_env(tmp_path)) is current
    )
    assert adapter.confirm_calls == 1
    assert adapter.check_calls == 0
    assert adapter.refresh_calls == 0
    assert state.pending is None
    assert state.remove_calls == 1


@pytest.mark.asyncio
async def test_pending_confirmation_412_is_structured_and_kept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pending = credentials.PendingConfirmation(
        old_refresh_token=OLD_REFRESH_TOKEN,
        new_refresh_token=NEW_REFRESH_TOKEN,
    )
    state = _install_persistence(monkeypatch, tmp_path, pending=pending)
    adapter = _FakeAdapter()
    adapter.confirm_error = RiskControlError(retry_after=123)
    coordinator = CookieRefreshCoordinator(adapter=adapter)

    with pytest.raises(RiskControlError) as exc_info:
        await coordinator.maybe_refresh(
            _credential(refreshed=True), env=_enabled_env(tmp_path)
        )

    assert exc_info.value.retry_after == 123
    assert state.pending is pending
    assert adapter.check_calls == 0
    assert adapter.refresh_calls == 0


@pytest.mark.asyncio
async def test_rotating_environment_override_is_rejected_without_secret(
    tmp_path: Path,
) -> None:
    env = _enabled_env(tmp_path)
    env["SESSDATA"] = "must-not-appear"
    coordinator = CookieRefreshCoordinator(adapter=_FakeAdapter())

    with pytest.raises(CookieRefreshConfigError) as exc_info:
        await coordinator.maybe_refresh(_credential(), env=env)

    assert "SESSDATA" in str(exc_info.value)
    assert "must-not-appear" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_raw_check_avoids_sdk_request_log_and_maps_http_412(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 412

        def json(self) -> dict[str, Any]:
            pytest.fail("412 response body must not be read")

    class Client:
        async def request(self, *_args: Any, **_kwargs: Any) -> Response:
            return Response()

    monkeypatch.setattr(cookie_refresh, "get_shared_http_client", lambda: Client())
    monkeypatch.setattr(
        cookie_refresh,
        "record_risk_control_failure",
        lambda: SimpleNamespace(retry_after=321),
    )
    monkeypatch.setattr(
        Credential,
        "check_refresh",
        lambda _self: pytest.fail("public SDK check must not be called"),
    )

    adapter = cookie_refresh._SdkCookieRefreshAdapter()
    with pytest.raises(RiskControlError) as exc_info:
        await adapter.check_refresh(_credential())

    assert exc_info.value.retry_after == 321


@pytest.mark.asyncio
async def test_raw_confirm_includes_sdk_compatible_csrf_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = {
        "called": False,
        "csrf_fields_match": False,
        "redirects_disabled": False,
    }

    class Response:
        status_code = 200

        def json(self) -> dict[str, int]:
            return {"code": 0}

    class Client:
        async def request(self, *_args: Any, **kwargs: Any) -> Response:
            data = kwargs.get("data")
            observed["called"] = True
            observed["csrf_fields_match"] = bool(
                isinstance(data, dict)
                and data.get("csrf") == NEW_CSRF
                and data.get("csrf_token") == NEW_CSRF
                and data.get("refresh_token") == OLD_REFRESH_TOKEN
            )
            observed["redirects_disabled"] = kwargs.get("follow_redirects") is False
            return Response()

    monkeypatch.setattr(cookie_refresh, "get_shared_http_client", lambda: Client())
    monkeypatch.setattr(cookie_refresh, "record_risk_control_success", lambda: None)

    adapter = cookie_refresh._SdkCookieRefreshAdapter()
    await adapter.confirm(OLD_REFRESH_TOKEN, _credential(refreshed=True))

    assert observed == {
        "called": True,
        "csrf_fields_match": True,
        "redirects_disabled": True,
    }


def test_sdk_private_contract_accepts_pinned_17_4_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cookie_refresh, "_sdk_compatibility_checked", False)

    cookie_refresh._SdkCookieRefreshAdapter()

    assert cookie_refresh._SUPPORTED_SDK_VERSION == "17.4.2"


def test_sdk_private_contract_rejects_unpinned_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cookie_refresh, "_sdk_compatibility_checked", False)
    monkeypatch.setattr(cookie_refresh.metadata, "version", lambda _name: "17.4.3")

    with pytest.raises(CookieRefreshError) as exc_info:
        cookie_refresh._SdkCookieRefreshAdapter()

    assert "17.4.3" not in str(exc_info.value)


def test_sdk_private_contract_rejects_unexpected_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = copy.deepcopy(cookie_refresh.sdk_network.API)
    api["info"]["check_cookies"][
        "url"
    ] = "https://example.invalid/x/passport-login/web/cookie/info"
    monkeypatch.setattr(cookie_refresh, "_sdk_compatibility_checked", False)
    monkeypatch.setattr(cookie_refresh.sdk_network, "API", api)

    with pytest.raises(CookieRefreshError):
        cookie_refresh._SdkCookieRefreshAdapter()


def test_enabled_runtime_validates_sdk_compatibility_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def validate() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(cookie_refresh, "_assert_sdk_compatibility", validate)

    cookie_refresh.validate_cookie_refresh_runtime({})
    cookie_refresh.validate_cookie_refresh_runtime(
        {"BILI_ENABLE_COOKIE_REFRESH": "true"}
    )

    assert calls == 1
