"""Interactively create initial local files for safe Cookie refresh."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import warnings
from pathlib import Path
from typing import Sequence

from .credentials import (
    CredentialLoadError,
    parse_cookie_text,
    write_cookie_file,
    write_refresh_token_file,
)

DEFAULT_INTERVAL_SECONDS = 21600
MIN_INTERVAL_SECONDS = 60
COOKIE_FILE_NAME = "bili-cookie.txt"
REFRESH_TOKEN_FILE_NAME = "bili-refresh-token.txt"


class SetupError(ValueError):
    """Raised when initial credential-file setup cannot be completed safely."""


def _normalize_cookie_header(raw_header: str) -> str:
    header = raw_header.strip()
    if header[:7].casefold() == "cookie:":
        header = header.split(":", 1)[1].strip()
    if not header:
        raise SetupError("Cookie header cannot be empty")
    return header


def _normalize_refresh_token(raw_token: str) -> str:
    token = raw_token.strip()
    if not token:
        raise SetupError("Refresh token cannot be empty")
    if "\n" in token or "\r" in token:
        raise SetupError("Refresh token must be one line")
    return token


def _require_refresh_cookie_fields(cookies: dict[str, str]) -> None:
    missing = [
        name
        for name, field in (("SESSDATA", "sessdata"), ("bili_jct", "bili_jct"))
        if not cookies.get(field)
    ]
    if missing:
        raise SetupError("Cookie header is missing: " + ", ".join(missing))


def _is_in_project(directory: Path) -> bool:
    project_root = Path(__file__).resolve().parents[1]
    return (project_root / "pyproject.toml").is_file() and directory.is_relative_to(
        project_root
    )


def create_credential_files(
    directory: Path,
    cookie_header: str,
    refresh_token: str,
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> dict[str, str]:
    """Validate interactive values and atomically create the two credential files."""
    if interval_seconds < MIN_INTERVAL_SECONDS:
        raise SetupError(
            f"Refresh interval must be at least {MIN_INTERVAL_SECONDS} seconds"
        )

    target_directory = directory.expanduser().resolve()
    if _is_in_project(target_directory):
        raise SetupError("Choose a directory outside this repository")

    cookie_path = target_directory / COOKIE_FILE_NAME
    refresh_token_path = target_directory / REFRESH_TOKEN_FILE_NAME
    existing = [
        path.name for path in (cookie_path, refresh_token_path) if path.exists()
    ]
    if existing:
        raise SetupError(
            "Refusing to overwrite existing file(s): " + ", ".join(existing)
        )

    try:
        cookies = parse_cookie_text(_normalize_cookie_header(cookie_header))
    except CredentialLoadError:
        raise SetupError("Cookie header has no supported Cookie values") from None
    _require_refresh_cookie_fields(cookies)
    token = _normalize_refresh_token(refresh_token)

    try:
        write_cookie_file(cookie_path, cookies)
    except CredentialLoadError:
        raise SetupError("Unable to create credential files") from None

    try:
        write_refresh_token_file(refresh_token_path, token)
    except CredentialLoadError:
        try:
            cookie_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise SetupError("Unable to create credential files") from None

    return {
        "BILI_COOKIE_FILE": str(cookie_path),
        "BILI_REFRESH_TOKEN_FILE": str(refresh_token_path),
        "BILI_ENABLE_COOKIE_REFRESH": "true",
        "BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS": str(interval_seconds),
    }


def _read_hidden(prompt: str) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except getpass.GetPassWarning:
        raise SetupError(
            "Hidden terminal input is unavailable; do not enter secrets"
        ) from None
    except (EOFError, KeyboardInterrupt):
        raise SetupError("Setup cancelled") from None


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create local Cookie-refresh files from two pasted browser values."
    )
    parser.add_argument(
        "--directory",
        required=True,
        type=Path,
        help="Existing or new directory outside this repository for the two files.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Refresh-check interval in seconds (minimum {MIN_INTERVAL_SECONDS}).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        cookie_header = _read_hidden(
            "Paste the Cookie header value (input is hidden), then press Enter: "
        )
        refresh_token = _read_hidden(
            "Paste ac_time_value (input is hidden), then press Enter: "
        )
        env = create_credential_files(
            args.directory,
            cookie_header,
            refresh_token,
            interval_seconds=args.interval,
        )
    except SetupError as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 2

    print("Credential files created. Add this non-secret env block to your MCP config:")
    print(json.dumps(env, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
