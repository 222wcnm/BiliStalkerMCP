"""Read-only local diagnostics for the CLI."""

from __future__ import annotations

import os
import socket
import sys
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import __version__


def _present(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _file_writable(path: Path) -> bool:
    try:
        return (
            path.is_file()
            and not path.is_symlink()
            and os.access(path, os.R_OK | os.W_OK)
            and os.access(path.parent, os.W_OK)
        )
    except (OSError, ValueError):
        return False


def run_doctor(*, network: bool = False) -> dict[str, Any]:
    """Inspect configuration without starting the server or changing credentials."""
    from .credentials import (
        CredentialLoadError,
        load_cookie_file,
        read_refresh_token_file,
        resolve_cookie_refresh_file_paths,
    )

    checks: dict[str, dict[str, Any]] = {
        "runtime": {
            "status": "ok",
            "python": sys.version.split()[0],
            "package": __version__,
        }
    }

    dependencies: dict[str, str] = {}
    missing: list[str] = []
    for package in ("bilibili-api-python", "fastmcp", "mcp", "httpx", "curl_cffi"):
        try:
            dependencies[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            missing.append(package)
    checks["dependencies"] = {
        "status": (
            "error"
            if missing or dependencies.get("bilibili-api-python") != "17.4.2"
            else "ok"
        ),
        "versions": dependencies,
        "missing": missing,
        "sdk_version_matches_pin": dependencies.get("bilibili-api-python") == "17.4.2",
    }

    cookie_values: dict[str, str] = {}
    cookie_path_raw = os.environ.get("BILI_COOKIE_FILE", "").strip()
    credential_issues: list[str] = []
    if cookie_path_raw:
        try:
            cookie_values = load_cookie_file(cookie_path_raw)
        except CredentialLoadError:
            credential_issues.append("cookie_file_unreadable_or_invalid")

    credential_source = (
        "environment"
        if _present("SESSDATA")
        else "cookie_file" if cookie_values.get("sessdata") else "none"
    )
    if credential_source == "none":
        credential_issues.append("sessdata_missing")
    checks["credential"] = {
        "status": "error" if credential_issues else "ok",
        "source": credential_source,
        "cookie_file_configured": bool(cookie_path_raw),
        "cookie_file_readable": bool(cookie_path_raw)
        and "cookie_file_unreadable_or_invalid" not in credential_issues,
        "issues": credential_issues,
    }

    refresh_raw = os.environ.get("BILI_ENABLE_COOKIE_REFRESH", "false").strip().lower()
    refresh_valid = refresh_raw in {"1", "true", "yes", "on", "0", "false", "no", "off"}
    refresh_enabled = refresh_raw in {"1", "true", "yes", "on"}
    token_path_raw = os.environ.get("BILI_REFRESH_TOKEN_FILE", "").strip()
    token_present = False
    refresh_issues: list[str] = []
    if not refresh_valid:
        refresh_issues.append("invalid_refresh_toggle")
    if token_path_raw:
        try:
            token_present = bool(read_refresh_token_file(token_path_raw))
        except CredentialLoadError:
            refresh_issues.append("token_file_unreadable_or_invalid")

    if refresh_enabled:
        if not cookie_path_raw or not token_path_raw:
            refresh_issues.append("refresh_files_missing")
        if not cookie_values.get("sessdata") or not cookie_values.get("bili_jct"):
            refresh_issues.append("required_cookie_fields_missing")
        if not token_present:
            refresh_issues.append("refresh_token_missing")
        if any(_present(name) for name in ("SESSDATA", "BILI_JCT", "DEDEUSERID")):
            refresh_issues.append("rotating_cookie_env_override")
        if cookie_path_raw and token_path_raw:
            try:
                files = resolve_cookie_refresh_file_paths()
                if not _file_writable(files.cookie_path):
                    refresh_issues.append("cookie_file_not_writable")
                if not _file_writable(files.refresh_token_path):
                    refresh_issues.append("token_file_not_writable")
            except CredentialLoadError:
                refresh_issues.append("refresh_paths_invalid")
    checks["refresh"] = {
        "status": "error" if refresh_issues else "ok",
        "enabled": refresh_enabled,
        "token_file_configured": bool(token_path_raw),
        "token_present": token_present,
        "issues": refresh_issues,
    }

    proxy_raw = os.environ.get("BILI_PROXY", "").strip()
    proxy_host: str | None = None
    proxy_port: int | None = None
    proxy_scheme: str | None = None
    proxy_error = False
    if proxy_raw:
        try:
            parts = urlsplit(proxy_raw)
            proxy_host = parts.hostname
            proxy_port = parts.port or (443 if parts.scheme == "https" else 80)
            proxy_scheme = parts.scheme
            proxy_error = not bool(proxy_host and proxy_scheme)
        except ValueError:
            proxy_error = True
    checks["proxy"] = {
        "status": "error" if proxy_error else "ok",
        "configured": bool(proxy_raw),
        "scheme": proxy_scheme,
    }

    if network:
        target = "proxy" if proxy_raw and not proxy_error else "bilibili"
        host = proxy_host if target == "proxy" else "api.bilibili.com"
        port = proxy_port if target == "proxy" else 443
        try:
            assert host is not None and port is not None
            with socket.create_connection((host, port), timeout=3):
                pass
            status = "ok"
        except OSError:
            status = "error"
        checks["network"] = {"status": status, "target": target, "kind": "tcp"}

    return {
        "ok": all(check["status"] == "ok" for check in checks.values()),
        "checks": checks,
    }
