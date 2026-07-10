"""Credential loading helpers for Bilibili cookies and refresh tokens."""

from __future__ import annotations

import logging
import os
import stat
import tempfile
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from typing import Mapping

from bilibili_api import Credential

logger = logging.getLogger(__name__)

BILI_COOKIE_FILE_ENV = "BILI_COOKIE_FILE"
BILI_REFRESH_TOKEN_FILE_ENV = "BILI_REFRESH_TOKEN_FILE"
BILI_ENABLE_COOKIE_REFRESH_ENV = "BILI_ENABLE_COOKIE_REFRESH"

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

OWNER_READ_WRITE = stat.S_IRUSR | stat.S_IWUSR


class CredentialLoadError(ValueError):
    """Raised when a configured credential file cannot be safely loaded."""


@dataclass(frozen=True)
class CredentialSnapshot:
    """Plain credential values before constructing bilibili_api.Credential."""

    sessdata: str | None = None
    bili_jct: str | None = None
    buvid3: str | None = None
    buvid4: str | None = None
    dedeuserid: str | None = None
    refresh_token: str | None = None
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


def _credential_file_path(raw_path: str | os.PathLike[str]) -> Path:
    return Path(raw_path).expanduser()


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
    except CookieError as exc:
        raise CredentialLoadError(f"Invalid {BILI_COOKIE_FILE_ENV} format") from exc

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
    except OSError as exc:
        raise CredentialLoadError(
            f"Unable to read {BILI_COOKIE_FILE_ENV} at {cookie_path}"
        ) from exc

    try:
        return parse_cookie_text(text)
    except CredentialLoadError as exc:
        raise CredentialLoadError(
            f"Invalid {BILI_COOKIE_FILE_ENV} at {cookie_path}: {exc}"
        ) from exc


def read_refresh_token_file(path: str | os.PathLike[str]) -> str | None:
    token_path = _credential_file_path(path)
    try:
        return _clean_secret(token_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CredentialLoadError(
            f"Unable to read {BILI_REFRESH_TOKEN_FILE_ENV} at {token_path}"
        ) from exc


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
        "Invalid boolean value for %s=%r, falling back to False",
        BILI_ENABLE_COOKIE_REFRESH_ENV,
        raw,
    )
    return False


def load_credential_snapshot(
    env: Mapping[str, str] | None = None,
) -> CredentialSnapshot:
    source = os.environ if env is None else env
    values: dict[str, str] = {}

    cookie_file = _clean_secret(source.get(BILI_COOKIE_FILE_ENV))
    if cookie_file is not None:
        values.update(load_cookie_file(cookie_file))

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
        refresh_token=load_refresh_token(source),
        refresh_enabled=cookie_refresh_enabled(source),
    )


def _is_posix() -> bool:
    return os.name == "posix"


def _set_owner_only_permissions(path: Path) -> None:
    if not _is_posix():
        return

    try:
        os.chmod(path, OWNER_READ_WRITE)
    except OSError:
        logger.debug("Unable to chmod credential file %s", path, exc_info=True)


def write_refresh_token_file(path: str | os.PathLike[str], token: str) -> None:
    token_path = _credential_file_path(path)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{token_path.name}.",
        suffix=".tmp",
        dir=token_path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_clean_secret(token) or "")
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        _set_owner_only_permissions(tmp_path)
        os.replace(tmp_path, token_path)
        _set_owner_only_permissions(token_path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


__all__ = [
    "BILI_COOKIE_FILE_ENV",
    "BILI_ENABLE_COOKIE_REFRESH_ENV",
    "BILI_REFRESH_TOKEN_FILE_ENV",
    "CredentialLoadError",
    "CredentialSnapshot",
    "cookie_refresh_enabled",
    "load_cookie_file",
    "load_credential_snapshot",
    "load_refresh_token",
    "parse_cookie_text",
    "read_refresh_token_file",
    "write_refresh_token_file",
]
