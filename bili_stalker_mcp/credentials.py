"""Credential loading helpers for Bilibili cookies and refresh tokens."""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from typing import Any, Mapping

from bilibili_api import Credential
from filelock import FileLock
from filelock import Timeout as FileLockTimeout

logger = logging.getLogger(__name__)

BILI_COOKIE_FILE_ENV = "BILI_COOKIE_FILE"
BILI_REFRESH_TOKEN_FILE_ENV = "BILI_REFRESH_TOKEN_FILE"
BILI_ENABLE_COOKIE_REFRESH_ENV = "BILI_ENABLE_COOKIE_REFRESH"

COOKIE_REFRESH_TRANSACTION_MARKER = ".bili-cookie-refresh-transaction.json"
COOKIE_REFRESH_COOKIE_STAGE = ".bili-cookie-refresh-cookie.stage"
COOKIE_REFRESH_TOKEN_STAGE = ".bili-cookie-refresh-token.stage"
COOKIE_REFRESH_PENDING_CONFIRM = ".bili-cookie-refresh-pending.json"
COOKIE_REFRESH_LOCK_FILE = ".bili-cookie-refresh.lock"
COOKIE_REFRESH_LOCK_TIMEOUT_SECONDS = 180

TRANSACTION_VERSION = 1

COOKIE_ENV_TO_FIELD = {
    "SESSDATA": "sessdata",
    "BILI_JCT": "bili_jct",
    "BUVID3": "buvid3",
    "BUVID4": "buvid4",
    "DEDEUSERID": "dedeuserid",
}

COOKIE_NAME_TO_FIELD = {
    "sessdata": "sessdata",
    "bili_jct": "bili_jct",
    "buvid3": "buvid3",
    "buvid4": "buvid4",
    "dedeuserid": "dedeuserid",
}

COOKIE_FIELD_TO_NAME = {
    "sessdata": "SESSDATA",
    "bili_jct": "bili_jct",
    "buvid3": "buvid3",
    "buvid4": "buvid4",
    "dedeuserid": "DedeUserID",
}

ROTATING_COOKIE_ENV_NAMES = ("SESSDATA", "BILI_JCT", "DEDEUSERID")

OWNER_READ_WRITE = stat.S_IRUSR | stat.S_IWUSR


class CredentialLoadError(ValueError):
    """Raised when a configured credential file cannot be safely loaded."""


class CredentialPersistenceError(CredentialLoadError):
    """Raised when refreshed credential state cannot be safely persisted."""


@dataclass(frozen=True)
class CookieRefreshFiles:
    """Validated filesystem targets used by automatic cookie refresh."""

    cookie_path: Path
    refresh_token_path: Path

    @property
    def lock_path(self) -> Path:
        return self.refresh_token_path.parent / COOKIE_REFRESH_LOCK_FILE


@dataclass(frozen=True)
class PendingConfirmation:
    """Protected state retained until the old refresh token is confirmed."""

    old_refresh_token: str = field(repr=False)
    new_refresh_token: str = field(repr=False)


@dataclass(frozen=True)
class CredentialSnapshot:
    """Plain credential values before constructing bilibili_api.Credential."""

    sessdata: str | None = field(default=None, repr=False)
    bili_jct: str | None = field(default=None, repr=False)
    buvid3: str | None = field(default=None, repr=False)
    buvid4: str | None = field(default=None, repr=False)
    dedeuserid: str | None = field(default=None, repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    refresh_enabled: bool = False

    def cache_key(self) -> tuple[str | bool | None, ...]:
        return (
            self.sessdata,
            self.bili_jct,
            self.buvid3,
            self.buvid4,
            self.dedeuserid,
            self.refresh_token,
            self.refresh_enabled,
        )

    def to_credential(self) -> Credential | None:
        if not self.sessdata:
            return None

        return Credential(
            sessdata=self.sessdata,
            bili_jct=self.bili_jct or "",
            buvid3=self.buvid3 or "",
            buvid4=self.buvid4 or "",
            dedeuserid=self.dedeuserid or "",
            ac_time_value=self.refresh_token if self.refresh_enabled else "",
        )


def _clean_secret(raw: str | None) -> str | None:
    if raw is None:
        return None

    value = raw.strip()
    if not value:
        return None
    return value


def _is_single_line_secret(value: str) -> bool:
    return not any(character in value for character in ("\x00", "\r", "\n"))


def _credential_file_path(raw_path: str | os.PathLike[str]) -> Path:
    return Path(raw_path).expanduser()


@dataclass(frozen=True)
class _TransactionArtifacts:
    cookie_target: Path
    refresh_token_target: Path
    marker: Path
    cookie_stage: Path
    refresh_token_stage: Path
    pending_confirmation: Path


def _absolute_credential_path(raw_path: str | os.PathLike[str]) -> Path:
    return _credential_file_path(raw_path).absolute()


def _transaction_artifacts(
    cookie_path: str | os.PathLike[str],
    refresh_token_path: str | os.PathLike[str],
) -> _TransactionArtifacts:
    cookie_target = _absolute_credential_path(cookie_path)
    refresh_token_target = _absolute_credential_path(refresh_token_path)
    reserved_names = {
        COOKIE_REFRESH_TRANSACTION_MARKER.casefold(),
        COOKIE_REFRESH_COOKIE_STAGE.casefold(),
        COOKIE_REFRESH_TOKEN_STAGE.casefold(),
        COOKIE_REFRESH_PENDING_CONFIRM.casefold(),
        COOKIE_REFRESH_LOCK_FILE.casefold(),
    }

    if cookie_target == refresh_token_target:
        raise CredentialPersistenceError(
            f"{BILI_COOKIE_FILE_ENV} and {BILI_REFRESH_TOKEN_FILE_ENV} must differ"
        )
    if (
        cookie_target.name.casefold() in reserved_names
        or refresh_token_target.name.casefold() in reserved_names
    ):
        raise CredentialPersistenceError(
            "Credential target conflicts with reserved refresh state"
        )

    return _TransactionArtifacts(
        cookie_target=cookie_target,
        refresh_token_target=refresh_token_target,
        marker=cookie_target.parent / COOKIE_REFRESH_TRANSACTION_MARKER,
        cookie_stage=cookie_target.parent / COOKIE_REFRESH_COOKIE_STAGE,
        refresh_token_stage=(refresh_token_target.parent / COOKIE_REFRESH_TOKEN_STAGE),
        pending_confirmation=(
            refresh_token_target.parent / COOKIE_REFRESH_PENDING_CONFIRM
        ),
    )


def _cookie_values_by_field(cookies: Mapping[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for name, raw_value in cookies.items():
        field_name = COOKIE_NAME_TO_FIELD.get(name.lower())
        if field_name is None and name in COOKIE_FIELD_TO_NAME:
            field_name = name
        if field_name is None:
            continue

        value = _clean_secret(raw_value)
        if value is not None:
            values[field_name] = value
    return values


def serialize_cookie_values(cookies: Mapping[str, str]) -> str:
    """Serialize only supported ordinary cookies, never refresh tokens."""
    values = _cookie_values_by_field(cookies)
    serialized: list[str] = []
    for field_name, cookie_name in COOKIE_FIELD_TO_NAME.items():
        value = values.get(field_name)
        if value is None:
            continue

        cookie = SimpleCookie()
        cookie[cookie_name] = value
        serialized.append(cookie[cookie_name].OutputString())

    if not serialized:
        raise CredentialPersistenceError(
            f"{BILI_COOKIE_FILE_ENV} did not contain supported cookie fields"
        )
    return "; ".join(serialized) + "\n"


def parse_cookie_text(text: str) -> dict[str, str]:
    """Parse a plain Cookie header text into supported credential fields."""
    if "\x00" in text:
        raise CredentialLoadError(f"Invalid {BILI_COOKIE_FILE_ENV} format")

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        return {}

    cookie = SimpleCookie()
    try:
        cookie.load("; ".join(lines))
    except CookieError:
        raise CredentialLoadError(f"Invalid {BILI_COOKIE_FILE_ENV} format") from None

    values: dict[str, str] = {}
    for cookie_name, morsel in cookie.items():
        field_name = COOKIE_NAME_TO_FIELD.get(cookie_name.lower())
        if field_name is None:
            continue

        value = _clean_secret(morsel.value)
        if value is not None:
            values[field_name] = value

    if not values:
        raise CredentialLoadError(
            f"{BILI_COOKIE_FILE_ENV} did not contain supported cookie fields"
        )

    return values


def load_cookie_file(path: str | os.PathLike[str]) -> dict[str, str]:
    cookie_path = _credential_file_path(path)
    try:
        text = cookie_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise CredentialLoadError(f"Unable to read {BILI_COOKIE_FILE_ENV}") from None

    try:
        return parse_cookie_text(text)
    except CredentialLoadError as exc:
        raise CredentialLoadError(f"Invalid {BILI_COOKIE_FILE_ENV}: {exc}") from None


def read_refresh_token_file(path: str | os.PathLike[str]) -> str | None:
    token_path = _credential_file_path(path)
    try:
        value = _clean_secret(token_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        raise CredentialLoadError(
            f"Unable to read {BILI_REFRESH_TOKEN_FILE_ENV}"
        ) from None
    if value is not None and not _is_single_line_secret(value):
        raise CredentialLoadError(f"Invalid {BILI_REFRESH_TOKEN_FILE_ENV} format")
    return value


def load_refresh_token(env: Mapping[str, str] | None = None) -> str | None:
    """Load refresh token only from BILI_REFRESH_TOKEN_FILE."""
    source = os.environ if env is None else env
    token_file = _clean_secret(source.get(BILI_REFRESH_TOKEN_FILE_ENV))
    if token_file is None:
        return None
    return read_refresh_token_file(token_file)


def cookie_refresh_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    raw = source.get(BILI_ENABLE_COOKIE_REFRESH_ENV)
    if raw is None:
        return False

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logger.warning(
        "Invalid boolean value for %s; falling back to False",
        BILI_ENABLE_COOKIE_REFRESH_ENV,
    )
    return False


def _validate_refresh_target(path: Path, env_name: str) -> None:
    try:
        target_is_safe = path.is_file() and not path.is_symlink()
        target_is_read_write = os.access(path, os.R_OK | os.W_OK)
        parent_mode = os.W_OK | (os.X_OK if _is_posix() else 0)
        parent_is_writable = os.access(path.parent, parent_mode)
    except OSError:
        target_is_safe = False
        target_is_read_write = False
        parent_is_writable = False

    if not (target_is_safe and target_is_read_write and parent_is_writable):
        raise CredentialLoadError(
            f"{env_name} must reference a readable and writable regular file"
        )


def _validate_enabled_refresh_configuration(
    source: Mapping[str, str],
    cookie_path: Path,
    refresh_token_path: Path,
    cookie_values: Mapping[str, str],
    refresh_token: str | None,
) -> None:
    overrides = [
        name
        for name in ROTATING_COOKIE_ENV_NAMES
        if _clean_secret(source.get(name)) is not None
    ]
    if overrides:
        raise CredentialLoadError(
            "Cookie refresh does not allow environment overrides: "
            + ", ".join(overrides)
        )

    _validate_refresh_target(cookie_path, BILI_COOKIE_FILE_ENV)
    _validate_refresh_target(refresh_token_path, BILI_REFRESH_TOKEN_FILE_ENV)

    missing_fields = [
        env_name
        for env_name, field_name in (
            ("SESSDATA", "sessdata"),
            ("BILI_JCT", "bili_jct"),
        )
        if not cookie_values.get(field_name)
    ]
    if missing_fields:
        raise CredentialLoadError(
            f"{BILI_COOKIE_FILE_ENV} missing required fields: "
            + ", ".join(missing_fields)
        )
    if refresh_token is None:
        raise CredentialLoadError(
            f"{BILI_REFRESH_TOKEN_FILE_ENV} must contain a refresh token"
        )


def resolve_cookie_refresh_file_paths(
    env: Mapping[str, str] | None = None,
) -> CookieRefreshFiles:
    """Resolve refresh targets without reading or recovering credential files."""
    source = os.environ if env is None else env
    cookie_file = _clean_secret(source.get(BILI_COOKIE_FILE_ENV))
    refresh_token_file = _clean_secret(source.get(BILI_REFRESH_TOKEN_FILE_ENV))
    missing_names = [
        env_name
        for env_name, value in (
            (BILI_COOKIE_FILE_ENV, cookie_file),
            (BILI_REFRESH_TOKEN_FILE_ENV, refresh_token_file),
        )
        if value is None
    ]
    if missing_names:
        raise CredentialLoadError(
            "Missing required cookie refresh configuration: " + ", ".join(missing_names)
        )

    overrides = [
        name
        for name in ROTATING_COOKIE_ENV_NAMES
        if _clean_secret(source.get(name)) is not None
    ]
    if overrides:
        raise CredentialLoadError(
            "Cookie refresh does not allow environment overrides: "
            + ", ".join(overrides)
        )

    assert cookie_file is not None
    assert refresh_token_file is not None
    files = CookieRefreshFiles(
        cookie_path=_absolute_credential_path(cookie_file),
        refresh_token_path=_absolute_credential_path(refresh_token_file),
    )
    _transaction_artifacts(files.cookie_path, files.refresh_token_path)
    return files


def load_credential_snapshot_unlocked(
    env: Mapping[str, str] | None = None,
) -> CredentialSnapshot:
    """Load a snapshot while the caller owns the refresh file lock, if enabled."""
    source = os.environ if env is None else env
    values: dict[str, str] = {}
    refresh_enabled = cookie_refresh_enabled(source)

    cookie_file = _clean_secret(source.get(BILI_COOKIE_FILE_ENV))
    refresh_token_file = _clean_secret(source.get(BILI_REFRESH_TOKEN_FILE_ENV))

    if refresh_enabled:
        files = resolve_cookie_refresh_file_paths(source)
        cookie_file = str(files.cookie_path)
        refresh_token_file = str(files.refresh_token_path)

    if cookie_file is not None and refresh_token_file is not None:
        recover_credential_transaction(cookie_file, refresh_token_file)

    if cookie_file is not None:
        values.update(load_cookie_file(cookie_file))

    refresh_token = (
        read_refresh_token_file(refresh_token_file)
        if refresh_token_file is not None
        else None
    )

    if refresh_enabled:
        assert cookie_file is not None
        assert refresh_token_file is not None
        _validate_enabled_refresh_configuration(
            source,
            _absolute_credential_path(cookie_file),
            _absolute_credential_path(refresh_token_file),
            values,
            refresh_token,
        )

    for env_name, field_name in COOKIE_ENV_TO_FIELD.items():
        value = _clean_secret(source.get(env_name))
        if value is not None:
            values[field_name] = value

    return CredentialSnapshot(
        sessdata=values.get("sessdata"),
        bili_jct=values.get("bili_jct"),
        buvid3=values.get("buvid3"),
        buvid4=values.get("buvid4"),
        dedeuserid=values.get("dedeuserid"),
        refresh_token=refresh_token,
        refresh_enabled=refresh_enabled,
    )


def load_credential_snapshot(
    env: Mapping[str, str] | None = None,
) -> CredentialSnapshot:
    source = os.environ if env is None else env
    if not cookie_refresh_enabled(source):
        return load_credential_snapshot_unlocked(source)

    files = resolve_cookie_refresh_file_paths(source)
    lock = FileLock(
        str(files.lock_path),
        timeout=COOKIE_REFRESH_LOCK_TIMEOUT_SECONDS,
    )
    try:
        with lock:
            return load_credential_snapshot_unlocked(source)
    except FileLockTimeout:
        raise CredentialLoadError(
            "Timed out waiting for Bilibili credential refresh lock."
        ) from None
    except OSError:
        raise CredentialLoadError(
            "Unable to access Bilibili credential refresh lock."
        ) from None


def resolve_cookie_refresh_files(
    env: Mapping[str, str] | None = None,
) -> CookieRefreshFiles | None:
    """Return validated refresh file targets, or None when refresh is disabled."""
    source = os.environ if env is None else env
    if not cookie_refresh_enabled(source):
        return None

    files = resolve_cookie_refresh_file_paths(source)
    load_credential_snapshot(source)
    return files


def _is_posix() -> bool:
    return os.name == "posix"


def _set_owner_only_permissions(path: Path) -> None:
    if not _is_posix():
        return

    try:
        os.chmod(path, OWNER_READ_WRITE)
    except OSError as exc:
        logger.debug(
            "Unable to set owner-only credential permissions (%s)",
            type(exc).__name__,
        )


def _fsync_parent_directory(path: Path) -> None:
    if not _is_posix():
        return

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path.parent, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        logger.debug(
            "Unable to fsync credential directory (%s)",
            type(exc).__name__,
        )


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_prefix = f"{path.name}." if path.name.startswith(".") else f".{path.name}."
    fd, tmp_name = tempfile.mkstemp(
        prefix=tmp_prefix,
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)

    try:
        _set_owner_only_permissions(tmp_path)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(tmp_path, path)
        _set_owner_only_permissions(path)
        _fsync_parent_directory(path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def write_cookie_file(path: str | os.PathLike[str], cookies: Mapping[str, str]) -> None:
    """Atomically write supported cookies without any refresh token fields."""
    cookie_path = _credential_file_path(path)
    try:
        _atomic_write_text(cookie_path, serialize_cookie_values(cookies))
    except CredentialPersistenceError:
        raise
    except Exception as exc:
        raise CredentialPersistenceError(
            f"Unable to write {BILI_COOKIE_FILE_ENV} ({type(exc).__name__})"
        ) from None


def write_refresh_token_file(path: str | os.PathLike[str], token: str) -> None:
    token_path = _credential_file_path(path)
    cleaned_token = _clean_secret(token)
    if cleaned_token is not None and not _is_single_line_secret(cleaned_token):
        raise CredentialPersistenceError(
            f"Invalid {BILI_REFRESH_TOKEN_FILE_ENV} format"
        )
    try:
        _atomic_write_text(token_path, (cleaned_token or "") + "\n")
    except Exception as exc:
        raise CredentialPersistenceError(
            f"Unable to write {BILI_REFRESH_TOKEN_FILE_ENV} " f"({type(exc).__name__})"
        ) from None


def _marker_payload(artifacts: _TransactionArtifacts) -> dict[str, Any]:
    return {
        "version": TRANSACTION_VERSION,
        "state": "prepared",
        "cookie_target": os.path.normcase(str(artifacts.cookie_target)),
        "refresh_token_target": os.path.normcase(str(artifacts.refresh_token_target)),
    }


def _write_transaction_marker(artifacts: _TransactionArtifacts) -> None:
    payload = json.dumps(
        _marker_payload(artifacts), sort_keys=True, separators=(",", ":")
    )
    _atomic_write_text(artifacts.marker, payload + "\n")


def _read_transaction_marker(artifacts: _TransactionArtifacts) -> None:
    if artifacts.marker.is_symlink():
        raise CredentialLoadError("Unsafe credential transaction marker")
    try:
        raw_payload = json.loads(artifacts.marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise CredentialLoadError("Invalid credential transaction marker") from None

    if raw_payload != _marker_payload(artifacts):
        raise CredentialLoadError("Invalid credential transaction marker")


def _pending_confirmation_path(
    refresh_token_path: str | os.PathLike[str],
) -> Path:
    token_target = _absolute_credential_path(refresh_token_path)
    return token_target.parent / COOKIE_REFRESH_PENDING_CONFIRM


def _pending_confirmation_text(old_refresh_token: str, new_refresh_token: str) -> str:
    payload = {
        "version": TRANSACTION_VERSION,
        "old_refresh_token": old_refresh_token,
        "new_refresh_token": new_refresh_token,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"


def _write_pending_confirmation(
    path: Path, old_refresh_token: str, new_refresh_token: str
) -> None:
    _atomic_write_text(
        path,
        _pending_confirmation_text(old_refresh_token, new_refresh_token),
    )


def read_pending_confirmation(
    refresh_token_path: str | os.PathLike[str],
) -> PendingConfirmation | None:
    """Read protected confirmation state without exposing tokens in errors."""
    path = _pending_confirmation_path(refresh_token_path)
    if path.is_symlink():
        raise CredentialLoadError("Unsafe pending cookie confirmation state")
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise CredentialLoadError("Invalid pending cookie confirmation state") from None

    if not isinstance(payload, dict) or set(payload) != {
        "version",
        "old_refresh_token",
        "new_refresh_token",
    }:
        raise CredentialLoadError("Invalid pending cookie confirmation state")
    old_refresh_token = payload.get("old_refresh_token")
    new_refresh_token = payload.get("new_refresh_token")
    if (
        payload.get("version") != TRANSACTION_VERSION
        or not isinstance(old_refresh_token, str)
        or not isinstance(new_refresh_token, str)
        or _clean_secret(old_refresh_token) != old_refresh_token
        or _clean_secret(new_refresh_token) != new_refresh_token
        or not _is_single_line_secret(old_refresh_token)
        or not _is_single_line_secret(new_refresh_token)
        or old_refresh_token == new_refresh_token
    ):
        raise CredentialLoadError("Invalid pending cookie confirmation state")

    return PendingConfirmation(
        old_refresh_token=old_refresh_token,
        new_refresh_token=new_refresh_token,
    )


def _unlink_state_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_parent_directory(path)


def remove_pending_confirmation(
    refresh_token_path: str | os.PathLike[str],
) -> None:
    """Remove pending state after the old token was confirmed remotely."""
    path = _pending_confirmation_path(refresh_token_path)
    if path.is_symlink():
        raise CredentialPersistenceError("Unsafe pending cookie confirmation state")
    try:
        _unlink_state_file(path)
    except OSError as exc:
        raise CredentialPersistenceError(
            "Unable to remove pending cookie confirmation state "
            f"({type(exc).__name__})"
        ) from None


def _discard_prepared_transaction(artifacts: _TransactionArtifacts) -> None:
    for path in (
        artifacts.cookie_stage,
        artifacts.refresh_token_stage,
        artifacts.marker,
    ):
        _unlink_state_file(path)


def _verify_pending_transaction_token(
    artifacts: _TransactionArtifacts, pending: PendingConfirmation
) -> None:
    token_source = (
        artifacts.refresh_token_stage
        if artifacts.refresh_token_stage.exists()
        else artifacts.refresh_token_target
    )
    if token_source.is_symlink():
        raise CredentialLoadError("Unsafe refresh token transaction state")
    current_token = read_refresh_token_file(token_source)
    if current_token != pending.new_refresh_token:
        raise CredentialLoadError(
            "Credential transaction does not match pending confirmation state"
        )


def _commit_staged_credentials(artifacts: _TransactionArtifacts) -> None:
    for stage, target in (
        (artifacts.cookie_stage, artifacts.cookie_target),
        (artifacts.refresh_token_stage, artifacts.refresh_token_target),
    ):
        if stage.is_symlink():
            raise CredentialPersistenceError("Unsafe staged credential state")
        if stage.exists():
            os.replace(stage, target)
            _set_owner_only_permissions(target)
            _fsync_parent_directory(target)
        elif not target.is_file() or target.is_symlink():
            raise CredentialPersistenceError("Incomplete credential transaction state")


def recover_credential_transaction(
    cookie_path: str | os.PathLike[str],
    refresh_token_path: str | os.PathLike[str],
) -> None:
    """Recover an interrupted two-file credential update before reading it."""
    artifacts = _transaction_artifacts(cookie_path, refresh_token_path)
    if artifacts.marker.is_symlink():
        raise CredentialLoadError("Unsafe credential transaction marker")
    if not artifacts.marker.exists():
        if not artifacts.pending_confirmation.exists():
            for stage in (
                artifacts.cookie_stage,
                artifacts.refresh_token_stage,
            ):
                if stage.exists():
                    _unlink_state_file(stage)
        return

    _read_transaction_marker(artifacts)
    pending = read_pending_confirmation(artifacts.refresh_token_target)
    if pending is None:
        try:
            _discard_prepared_transaction(artifacts)
        except OSError as exc:
            raise CredentialPersistenceError(
                "Unable to discard prepared credential transaction "
                f"({type(exc).__name__})"
            ) from None
        return

    try:
        _verify_pending_transaction_token(artifacts, pending)
        _commit_staged_credentials(artifacts)
        _verify_pending_transaction_token(artifacts, pending)
        _unlink_state_file(artifacts.marker)
    except CredentialLoadError:
        raise
    except OSError as exc:
        raise CredentialPersistenceError(
            f"Unable to recover credential transaction ({type(exc).__name__})"
        ) from None


def persist_refreshed_credentials(
    cookie_path: str | os.PathLike[str],
    refresh_token_path: str | os.PathLike[str],
    cookies: Mapping[str, str],
    refresh_token: str,
    old_refresh_token: str,
) -> None:
    """Persist refreshed cookies and token as one recoverable local transaction."""
    values = _cookie_values_by_field(cookies)
    missing_fields = [
        env_name
        for env_name, field_name in (
            ("SESSDATA", "sessdata"),
            ("BILI_JCT", "bili_jct"),
        )
        if not values.get(field_name)
    ]
    new_token = _clean_secret(refresh_token)
    old_token = _clean_secret(old_refresh_token)
    if missing_fields:
        raise CredentialPersistenceError(
            f"{BILI_COOKIE_FILE_ENV} missing required fields: "
            + ", ".join(missing_fields)
        )
    if new_token is None:
        raise CredentialPersistenceError(
            f"{BILI_REFRESH_TOKEN_FILE_ENV} must contain a refresh token"
        )
    if (
        old_token is None
        or not _is_single_line_secret(old_token)
        or not _is_single_line_secret(new_token)
        or old_token == new_token
    ):
        raise CredentialPersistenceError("Invalid refresh token rotation state")

    artifacts = _transaction_artifacts(cookie_path, refresh_token_path)
    recover_credential_transaction(cookie_path, refresh_token_path)
    if read_pending_confirmation(refresh_token_path) is not None:
        raise CredentialPersistenceError(
            "Pending cookie confirmation must be resolved before another refresh"
        )

    try:
        _atomic_write_text(
            artifacts.cookie_stage,
            serialize_cookie_values(values),
        )
        _atomic_write_text(artifacts.refresh_token_stage, new_token + "\n")
        _write_transaction_marker(artifacts)
        _write_pending_confirmation(
            artifacts.pending_confirmation,
            old_token,
            new_token,
        )
        _commit_staged_credentials(artifacts)
        _verify_pending_transaction_token(
            artifacts,
            PendingConfirmation(old_token, new_token),
        )
        _unlink_state_file(artifacts.marker)
    except CredentialLoadError:
        if not artifacts.pending_confirmation.exists():
            try:
                _discard_prepared_transaction(artifacts)
            except OSError as exc:
                raise CredentialPersistenceError(
                    "Unable to discard prepared credential transaction "
                    f"({type(exc).__name__})"
                ) from None
        raise
    except Exception as exc:
        if not artifacts.pending_confirmation.exists():
            try:
                _discard_prepared_transaction(artifacts)
            except OSError:
                pass
        raise CredentialPersistenceError(
            f"Unable to persist refreshed credentials ({type(exc).__name__})"
        ) from None


__all__ = [
    "BILI_COOKIE_FILE_ENV",
    "BILI_ENABLE_COOKIE_REFRESH_ENV",
    "BILI_REFRESH_TOKEN_FILE_ENV",
    "COOKIE_REFRESH_COOKIE_STAGE",
    "COOKIE_REFRESH_LOCK_FILE",
    "COOKIE_REFRESH_LOCK_TIMEOUT_SECONDS",
    "COOKIE_REFRESH_PENDING_CONFIRM",
    "COOKIE_REFRESH_TOKEN_STAGE",
    "COOKIE_REFRESH_TRANSACTION_MARKER",
    "CookieRefreshFiles",
    "CredentialLoadError",
    "CredentialPersistenceError",
    "CredentialSnapshot",
    "PendingConfirmation",
    "cookie_refresh_enabled",
    "load_cookie_file",
    "load_credential_snapshot",
    "load_credential_snapshot_unlocked",
    "load_refresh_token",
    "parse_cookie_text",
    "persist_refreshed_credentials",
    "read_refresh_token_file",
    "read_pending_confirmation",
    "recover_credential_transaction",
    "remove_pending_confirmation",
    "resolve_cookie_refresh_files",
    "resolve_cookie_refresh_file_paths",
    "serialize_cookie_values",
    "write_cookie_file",
    "write_refresh_token_file",
]
