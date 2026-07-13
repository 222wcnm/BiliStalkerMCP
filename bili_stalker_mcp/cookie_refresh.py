"""Safe, rate-limited coordination for Bilibili cookie rotation."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import time
import uuid
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, cast

from bilibili_api import Credential
from bilibili_api.utils import network as sdk_network
from filelock import AsyncFileLock
from filelock import Timeout as FileLockTimeout

from . import credentials
from .errors import RISK_CONTROL_CODES, RiskControlError, extract_error_code
from .infra.circuit_breaker import (
    ensure_risk_control_request_allowed,
    record_risk_control_failure,
    record_risk_control_success,
)
from .infra.http_client import get_shared_http_client

logger = logging.getLogger(__name__)

BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS_ENV = (
    "BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS"
)
DEFAULT_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS = 21600
MIN_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS = 60

_SUPPORTED_SDK_VERSION = "17.4.2"
_ROTATING_COOKIE_ENV_NAMES = ("SESSDATA", "BILI_JCT", "DEDEUSERID")
_REFRESH_CSRF_PATTERN = re.compile(r'<div id=["\']1-name["\']>([^<]+)</div>')

_sdk_compatibility_checked = False


class CookieRefreshError(RuntimeError):
    """Public-safe failure from refresh, confirmation, or local persistence."""


class CookieRefreshConfigError(CookieRefreshError):
    """Public-safe automatic refresh configuration failure."""

    def __init__(self, *fields: str) -> None:
        unique_fields = tuple(dict.fromkeys(fields))
        field_list = ", ".join(unique_fields) or "BILI_COOKIE_FILE"
        super().__init__(
            f"Invalid automatic cookie refresh configuration: {field_list}"
        )


class _SdkCompatibilityError(CookieRefreshError):
    """Raised when the pinned SDK private contract no longer matches."""


class _CookieRefreshAdapter(Protocol):
    async def check_refresh(self, credential: Credential) -> bool: ...

    async def refresh(self, credential: Credential) -> Credential: ...

    async def confirm(self, old_refresh_token: str, credential: Credential) -> None: ...


def _clean(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _check_interval_seconds(source: Mapping[str, str]) -> int:
    raw = source.get(BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS_ENV)
    if raw is None:
        return DEFAULT_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS

    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "Invalid integer value for %s; falling back to %s",
            BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS_ENV,
            DEFAULT_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS,
        )
        value = DEFAULT_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS

    return max(MIN_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS, value)


def _api_spec(group: str, name: str) -> Mapping[str, Any]:
    api = sdk_network.API
    return cast(Mapping[str, Any], api[group][name])


def _assert_sdk_compatibility() -> None:
    """Validate every SDK-private contract used by the isolated adapter."""
    global _sdk_compatibility_checked

    if _sdk_compatibility_checked:
        return

    try:
        if metadata.version("bilibili-api-python") != _SUPPORTED_SDK_VERSION:
            raise ValueError

        correspond_path = getattr(sdk_network, "_getCorrespondPath")
        if (
            not callable(correspond_path)
            or inspect.signature(correspond_path).parameters
        ):
            raise ValueError

        expected_specs = {
            ("info", "check_cookies"): (
                "GET",
                "https://passport.bilibili.com/x/passport-login/web/cookie/info",
            ),
            ("operate", "get_refresh_csrf"): (
                "GET",
                "https://www.bilibili.com/correspond/1/{correspondPath}",
            ),
            ("operate", "refresh_cookies"): (
                "POST",
                "https://passport.bilibili.com/x/passport-login/web/cookie/refresh",
            ),
            ("operate", "confirm_refresh"): (
                "POST",
                "https://passport.bilibili.com/x/passport-login/web/confirm/refresh",
            ),
        }
        for (group, name), (method, expected_url) in expected_specs.items():
            spec = _api_spec(group, name)
            if spec.get("method") != method:
                raise ValueError
            url = spec.get("url")
            if url != expected_url:
                raise ValueError

        credential_parameters = inspect.signature(Credential).parameters
        required_parameters = {
            "sessdata",
            "bili_jct",
            "buvid3",
            "buvid4",
            "dedeuserid",
            "ac_time_value",
        }
        if not required_parameters.issubset(credential_parameters):
            raise ValueError
        if not isinstance(sdk_network.HEADERS, dict):
            raise ValueError
    except Exception:
        raise _SdkCompatibilityError(
            "Installed bilibili-api-python is incompatible with safe cookie refresh."
        ) from None

    _sdk_compatibility_checked = True


def validate_cookie_refresh_runtime(
    env: Mapping[str, str] | None = None,
) -> None:
    """Fail server startup safely when enabled SDK internals are incompatible."""
    source = os.environ if env is None else env
    if credentials.cookie_refresh_enabled(source):
        _assert_sdk_compatibility()


def _risk_control_error_from_exception(exc: Exception) -> RiskControlError | None:
    if isinstance(exc, RiskControlError):
        return exc
    if extract_error_code(exc) not in RISK_CONTROL_CODES:
        return None

    snapshot = record_risk_control_failure()
    return RiskControlError(retry_after=snapshot.retry_after)


def _raise_risk_control() -> None:
    snapshot = record_risk_control_failure()
    raise RiskControlError(retry_after=snapshot.retry_after)


def _credential_identity(credential: Credential) -> tuple[str | None, ...]:
    return (
        credential.sessdata,
        credential.bili_jct,
        credential.buvid3,
        credential.buvid4,
        credential.dedeuserid,
        credential.ac_time_value,
    )


def _file_revision(
    files: credentials.CookieRefreshFiles,
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Return a secret-free revision used to detect another process's update."""
    try:
        cookie_stat = files.cookie_path.stat()
        token_stat = files.refresh_token_path.stat()
    except OSError:
        return None
    return (
        (cookie_stat.st_mtime_ns, cookie_stat.st_size),
        (token_stat.st_mtime_ns, token_stat.st_size),
    )


class _SdkCookieRefreshAdapter:
    """The only module boundary allowed to depend on SDK refresh internals.

    SDK 17.3.0 emits raw cookies, form data, and response bodies through its
    request-log event even when calling the low-level SDK client directly.  This
    adapter therefore reuses only its API metadata and correspondPath generator;
    requests use the project's non-logging raw client and are never retried.
    """

    def __init__(self) -> None:
        _assert_sdk_compatibility()

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        ensure_risk_control_request_allowed()
        try:
            return await get_shared_http_client().request(method, url, **kwargs)
        except Exception as exc:
            risk_error = _risk_control_error_from_exception(exc)
            if risk_error is not None:
                raise risk_error from None
            raise CookieRefreshError(
                "Bilibili cookie refresh request failed."
            ) from None

    @staticmethod
    def _payload(response: Any) -> Mapping[str, Any]:
        status_code = getattr(response, "status_code", None)
        if status_code in RISK_CONTROL_CODES:
            _raise_risk_control()
        if not isinstance(status_code, int) or status_code != 200:
            raise CookieRefreshError("Bilibili cookie refresh request failed.")

        try:
            payload = response.json()
        except Exception:
            raise CookieRefreshError(
                "Bilibili cookie refresh response was invalid."
            ) from None
        if not isinstance(payload, dict):
            raise CookieRefreshError("Bilibili cookie refresh response was invalid.")

        code = payload.get("code")
        if code in RISK_CONTROL_CODES:
            _raise_risk_control()
        if code != 0:
            raise CookieRefreshError("Bilibili cookie refresh request failed.")
        return payload

    @staticmethod
    def _request_cookies(
        credential: Credential, *, random_buvid3: bool
    ) -> dict[str, str]:
        cookies = {
            str(name): str(value)
            for name, value in credential.get_cookies().items()
            if value
        }
        if random_buvid3:
            cookies["buvid3"] = str(uuid.uuid4())
        return cookies

    async def check_refresh(self, credential: Credential) -> bool:
        spec = _api_spec("info", "check_cookies")
        response = await self._request(
            "GET",
            str(spec["url"]),
            cookies=self._request_cookies(credential, random_buvid3=False),
            headers=dict(sdk_network.HEADERS),
            follow_redirects=False,
        )
        payload = self._payload(response)
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("refresh"), bool):
            raise CookieRefreshError("Bilibili cookie refresh response was invalid.")
        record_risk_control_success()
        return bool(data["refresh"])

    async def _refresh_csrf(self, credential: Credential) -> str:
        try:
            correspond_path = sdk_network._getCorrespondPath()
        except Exception:
            raise CookieRefreshError(
                "Bilibili cookie refresh compatibility check failed."
            ) from None
        if (
            not isinstance(correspond_path, str)
            or re.fullmatch(r"[0-9a-f]{256}", correspond_path) is None
        ):
            raise CookieRefreshError(
                "Bilibili cookie refresh compatibility check failed."
            )

        spec = _api_spec("operate", "get_refresh_csrf")
        url = str(spec["url"]).replace("{correspondPath}", correspond_path)
        response = await self._request(
            "GET",
            url,
            cookies=self._request_cookies(credential, random_buvid3=True),
            headers=dict(sdk_network.HEADERS),
            follow_redirects=False,
        )
        status_code = getattr(response, "status_code", None)
        if status_code in RISK_CONTROL_CODES:
            _raise_risk_control()
        if not isinstance(status_code, int) or status_code != 200:
            raise CookieRefreshError("Bilibili cookie refresh request failed.")

        text = getattr(response, "text", None)
        if not isinstance(text, str):
            raise CookieRefreshError("Bilibili cookie refresh response was invalid.")
        match = _REFRESH_CSRF_PATTERN.search(text)
        if match is None or not match.group(1).strip():
            raise CookieRefreshError("Bilibili cookie refresh response was invalid.")
        return match.group(1).strip()

    async def refresh(self, credential: Credential) -> Credential:
        if not credential.bili_jct or not credential.ac_time_value:
            raise CookieRefreshConfigError(
                "BILI_COOKIE_FILE", "BILI_REFRESH_TOKEN_FILE"
            )

        refresh_csrf = await self._refresh_csrf(credential)
        spec = _api_spec("operate", "refresh_cookies")
        response = await self._request(
            "POST",
            str(spec["url"]),
            cookies=self._request_cookies(credential, random_buvid3=True),
            data={
                "csrf": credential.bili_jct,
                "refresh_csrf": refresh_csrf,
                "refresh_token": credential.ac_time_value,
                "source": "main_web",
            },
            headers=dict(sdk_network.HEADERS),
            follow_redirects=False,
        )
        payload = self._payload(response)
        data = payload.get("data")
        response_cookies = getattr(response, "cookies", None)
        if not isinstance(data, dict) or response_cookies is None:
            raise CookieRefreshError("Bilibili cookie refresh response was invalid.")

        try:
            sessdata = _clean(response_cookies.get("SESSDATA"))
            bili_jct = _clean(response_cookies.get("bili_jct"))
            dedeuserid = _clean(response_cookies.get("DedeUserID"))
            refresh_token = _clean(data.get("refresh_token"))
        except Exception:
            raise CookieRefreshError(
                "Bilibili cookie refresh response was invalid."
            ) from None
        if not sessdata or not bili_jct or not dedeuserid or not refresh_token:
            raise CookieRefreshError("Bilibili cookie refresh response was invalid.")

        return Credential(
            sessdata=sessdata,
            bili_jct=bili_jct,
            buvid3=credential.buvid3,
            buvid4=credential.buvid4,
            dedeuserid=dedeuserid,
            ac_time_value=refresh_token,
        )

    async def confirm(self, old_refresh_token: str, credential: Credential) -> None:
        if not credential.bili_jct or not old_refresh_token:
            raise CookieRefreshError("Bilibili cookie confirmation state was invalid.")

        spec = _api_spec("operate", "confirm_refresh")
        response = await self._request(
            "POST",
            str(spec["url"]),
            cookies=self._request_cookies(credential, random_buvid3=False),
            data={
                "csrf": credential.bili_jct,
                "csrf_token": credential.bili_jct,
                "refresh_token": old_refresh_token,
            },
            headers=dict(sdk_network.HEADERS),
            follow_redirects=False,
        )
        self._payload(response)
        record_risk_control_success()


class CookieRefreshCoordinator:
    """Serialize scheduled refresh checks and crash-safe confirmation retries."""

    def __init__(
        self,
        *,
        adapter: _CookieRefreshAdapter | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = asyncio.Lock()
        self._adapter = adapter
        self._clock = clock
        self._last_check: float | None = None
        self._file_key: tuple[Path, Path] | None = None
        self._latest_credential: Credential | None = None
        self._superseded_identity: tuple[str | None, ...] | None = None

    def _get_adapter(self) -> _CookieRefreshAdapter:
        if self._adapter is None:
            self._adapter = _SdkCookieRefreshAdapter()
        return self._adapter

    def _is_due(self, now: float, interval_seconds: int) -> bool:
        return self._last_check is None or now - self._last_check >= interval_seconds

    def _authoritative_credential(self, incoming: Credential) -> Credential:
        latest = self._latest_credential
        if latest is None:
            return incoming

        incoming_identity = _credential_identity(incoming)
        if incoming_identity in {
            _credential_identity(latest),
            self._superseded_identity,
        }:
            return latest
        return incoming

    @staticmethod
    def _resolve_files(source: Mapping[str, str]) -> credentials.CookieRefreshFiles:
        overridden = [
            name for name in _ROTATING_COOKIE_ENV_NAMES if _clean(source.get(name))
        ]
        if overridden:
            raise CookieRefreshConfigError(*overridden)

        missing = [
            name
            for name in (
                credentials.BILI_COOKIE_FILE_ENV,
                credentials.BILI_REFRESH_TOKEN_FILE_ENV,
            )
            if _clean(source.get(name)) is None
        ]
        if missing:
            raise CookieRefreshConfigError(*missing)

        try:
            files = credentials.resolve_cookie_refresh_file_paths(source)
        except Exception:
            raise CookieRefreshConfigError(
                credentials.BILI_COOKIE_FILE_ENV,
                credentials.BILI_REFRESH_TOKEN_FILE_ENV,
            ) from None
        return files

    @staticmethod
    def _load_current_credential(source: Mapping[str, str]) -> Credential:
        try:
            snapshot = credentials.load_credential_snapshot_unlocked(source)
            current = snapshot.to_credential()
        except Exception:
            raise CookieRefreshConfigError(
                credentials.BILI_COOKIE_FILE_ENV,
                credentials.BILI_REFRESH_TOKEN_FILE_ENV,
            ) from None
        if current is None or not current.sessdata or not current.bili_jct:
            raise CookieRefreshConfigError("BILI_COOKIE_FILE", "SESSDATA", "bili_jct")
        if not current.ac_time_value:
            raise CookieRefreshConfigError("BILI_REFRESH_TOKEN_FILE")
        return current

    def _reset_for_file_change(self, file_key: tuple[Path, Path]) -> None:
        self._file_key = file_key
        self._last_check = None
        self._latest_credential = None
        self._superseded_identity = None

    async def maybe_refresh(
        self,
        credential: Credential,
        *,
        env: Mapping[str, str] | None = None,
    ) -> Credential:
        source = os.environ if env is None else env
        if not credentials.cookie_refresh_enabled(source):
            return credential

        return await self.load_and_maybe_refresh(env=source, incoming=credential)

    async def load_and_maybe_refresh(
        self,
        *,
        env: Mapping[str, str] | None = None,
        incoming: Credential | None = None,
    ) -> Credential:
        """Load and refresh one request credential under process and file locks."""
        source = os.environ if env is None else env
        if not credentials.cookie_refresh_enabled(source):
            raise CookieRefreshConfigError(credentials.BILI_ENABLE_COOKIE_REFRESH_ENV)

        files = self._resolve_files(source)
        revision_before_lock = _file_revision(files)
        interval_seconds = _check_interval_seconds(source)

        async with self._lock:
            # Re-resolve configuration after waiting for another request, then keep
            # recovery, reads, refresh, persistence, and confirmation in one lock.
            files = self._resolve_files(source)
            file_lock = AsyncFileLock(
                str(files.lock_path),
                timeout=credentials.COOKIE_REFRESH_LOCK_TIMEOUT_SECONDS,
            )
            try:
                async with file_lock:
                    return await self._load_and_maybe_refresh_locked(
                        source,
                        files,
                        interval_seconds,
                        revision_before_lock,
                        incoming,
                    )
            except FileLockTimeout:
                raise CookieRefreshError(
                    "Timed out waiting for Bilibili credential refresh lock."
                ) from None
            except OSError:
                raise CookieRefreshError(
                    "Unable to access Bilibili credential refresh lock."
                ) from None

    async def _load_and_maybe_refresh_locked(
        self,
        source: Mapping[str, str],
        files: credentials.CookieRefreshFiles,
        interval_seconds: int,
        revision_before_lock: tuple[tuple[int, int], tuple[int, int]] | None,
        incoming: Credential | None,
    ) -> Credential:
        files = self._resolve_files(source)
        current = self._load_current_credential(source)
        if incoming is not None and _credential_identity(
            incoming
        ) == _credential_identity(current):
            current = incoming
        file_key = (files.cookie_path, files.refresh_token_path)
        if self._file_key != file_key:
            self._reset_for_file_change(file_key)

        authoritative = self._authoritative_credential(current)
        if authoritative is current:
            self._latest_credential = current
            self._superseded_identity = None
        current = authoritative
        now = self._clock()

        try:
            pending = credentials.read_pending_confirmation(files.refresh_token_path)
        except Exception:
            raise CookieRefreshError(
                "Stored Bilibili cookie confirmation state is invalid."
            ) from None

        adapter = self._get_adapter()
        if pending is not None:
            if current.ac_time_value != pending.new_refresh_token:
                raise CookieRefreshError(
                    "Stored Bilibili cookie confirmation state is inconsistent."
                )
            if not self._is_due(now, interval_seconds):
                return current

            self._last_check = now
            try:
                await adapter.confirm(pending.old_refresh_token, current)
            except RiskControlError:
                raise
            except Exception as exc:
                logger.warning(
                    "Bilibili cookie confirmation remains pending (%s)",
                    type(exc).__name__,
                )
                return current

            try:
                credentials.remove_pending_confirmation(files.refresh_token_path)
            except Exception:
                raise CookieRefreshError(
                    "Unable to remove Bilibili cookie confirmation state."
                ) from None
            return current

        revision_after_lock = _file_revision(files)
        if (
            revision_before_lock is not None
            and revision_after_lock is not None
            and revision_after_lock != revision_before_lock
        ):
            self._last_check = now
            return current

        if not self._is_due(now, interval_seconds):
            return current

        self._last_check = now
        try:
            refresh_required = await adapter.check_refresh(current)
        except RiskControlError:
            raise
        except _SdkCompatibilityError:
            raise
        except Exception as exc:
            logger.warning(
                "Bilibili cookie refresh check failed; current credential retained (%s)",
                type(exc).__name__,
            )
            return current

        if not refresh_required:
            return current

        old_identity = _credential_identity(current)
        try:
            refreshed = await adapter.refresh(current)
        except RiskControlError:
            raise
        except CookieRefreshConfigError:
            raise
        except Exception:
            raise CookieRefreshError(
                "Automatic Bilibili cookie refresh failed."
            ) from None

        if not (
            refreshed.sessdata
            and refreshed.bili_jct
            and refreshed.dedeuserid
            and refreshed.ac_time_value
        ):
            raise CookieRefreshError(
                "Automatic Bilibili cookie refresh returned invalid credentials."
            )

        cookie_values = {
            "sessdata": refreshed.sessdata,
            "bili_jct": refreshed.bili_jct,
            "buvid3": refreshed.buvid3 or "",
            "buvid4": refreshed.buvid4 or "",
            "dedeuserid": refreshed.dedeuserid,
        }
        try:
            credentials.persist_refreshed_credentials(
                files.cookie_path,
                files.refresh_token_path,
                cookie_values,
                refreshed.ac_time_value,
                current.ac_time_value or "",
            )
        except Exception:
            raise CookieRefreshError(
                "Unable to persist refreshed Bilibili credentials."
            ) from None

        self._latest_credential = refreshed
        self._superseded_identity = old_identity

        try:
            await adapter.confirm(current.ac_time_value or "", refreshed)
        except RiskControlError:
            raise
        except Exception as exc:
            logger.warning(
                "Bilibili cookie confirmation remains pending (%s)",
                type(exc).__name__,
            )
            return refreshed

        try:
            credentials.remove_pending_confirmation(files.refresh_token_path)
        except Exception:
            raise CookieRefreshError(
                "Unable to remove Bilibili cookie confirmation state."
            ) from None
        return refreshed


_coordinator = CookieRefreshCoordinator()


async def maybe_refresh_credential(credential: Credential) -> Credential:
    """Return the credential that the current MCP request must use."""
    return await _coordinator.maybe_refresh(credential)


async def load_refreshing_credential() -> Credential:
    """Load the current request credential under automatic-refresh locks."""
    return await _coordinator.load_and_maybe_refresh()


__all__ = [
    "BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS_ENV",
    "CookieRefreshConfigError",
    "CookieRefreshCoordinator",
    "CookieRefreshError",
    "load_refreshing_credential",
    "maybe_refresh_credential",
    "validate_cookie_refresh_runtime",
]
