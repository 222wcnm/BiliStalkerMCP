import logging
import stat
from pathlib import Path

import pytest

from bili_stalker_mcp import core, credentials

COOKIE_ENV_NAMES = (
    "SESSDATA",
    "BILI_JCT",
    "BUVID3",
    "BUVID4",
    "DEDEUSERID",
    "BILI_COOKIE_FILE",
    "BILI_REFRESH_TOKEN_FILE",
    "BILI_ENABLE_COOKIE_REFRESH",
    "AC_TIME_VALUE",
    "BILI_REFRESH_TOKEN",
)


@pytest.fixture(autouse=True)
def clean_credential_env(monkeypatch):
    for name in COOKIE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    _reset_core_credential_cache()
    yield
    _reset_core_credential_cache()


def _reset_core_credential_cache() -> None:
    core._credential_cache_key = None
    core._credential_cache_value = None
    core._missing_buvid3_warned = False


def _cookie_values(credential) -> dict[str, str]:
    assert credential is not None
    return credential.get_cookies()


def _write_cookie_file(
    path: Path,
    *,
    sessdata: str = "file_sessdata",
    bili_jct: str = "file_jct",
    buvid3: str = "file_buvid3",
    buvid4: str = "file_buvid4",
    dedeuserid: str = "file_dedeuserid",
) -> None:
    path.write_text(
        (
            f"SESSDATA={sessdata}; bili_jct={bili_jct}; "
            f"buvid3={buvid3}; buvid4={buvid4}; DedeUserID={dedeuserid}"
        ),
        encoding="utf-8",
    )


def test_env_only_credential(monkeypatch):
    monkeypatch.setenv("SESSDATA", "env_sessdata")
    monkeypatch.setenv("BILI_JCT", "env_jct")
    monkeypatch.setenv("BUVID3", "env_buvid3")
    monkeypatch.setenv("BUVID4", "env_buvid4")
    monkeypatch.setenv("DEDEUSERID", "env_dedeuserid")

    cookies = _cookie_values(core.get_credential())

    assert cookies["SESSDATA"] == "env_sessdata"
    assert cookies["bili_jct"] == "env_jct"
    assert cookies["buvid3"] == "env_buvid3"
    assert cookies["buvid4"] == "env_buvid4"
    assert cookies["DedeUserID"] == "env_dedeuserid"


def test_file_only_credential(monkeypatch, tmp_path):
    cookie_file = tmp_path / "cookie.txt"
    _write_cookie_file(cookie_file)
    monkeypatch.setenv("BILI_COOKIE_FILE", str(cookie_file))

    cookies = _cookie_values(core.get_credential())

    assert cookies["SESSDATA"] == "file_sessdata"
    assert cookies["bili_jct"] == "file_jct"
    assert cookies["buvid3"] == "file_buvid3"
    assert cookies["buvid4"] == "file_buvid4"
    assert cookies["DedeUserID"] == "file_dedeuserid"


def test_env_overrides_cookie_file(monkeypatch, tmp_path):
    cookie_file = tmp_path / "cookie.txt"
    _write_cookie_file(cookie_file)
    monkeypatch.setenv("BILI_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("SESSDATA", "env_sessdata")
    monkeypatch.setenv("BILI_JCT", "env_jct")
    monkeypatch.setenv("BUVID3", "env_buvid3")
    monkeypatch.setenv("BUVID4", "env_buvid4")
    monkeypatch.setenv("DEDEUSERID", "env_dedeuserid")

    cookies = _cookie_values(core.get_credential())

    assert cookies["SESSDATA"] == "env_sessdata"
    assert cookies["bili_jct"] == "env_jct"
    assert cookies["buvid3"] == "env_buvid3"
    assert cookies["buvid4"] == "env_buvid4"
    assert cookies["DedeUserID"] == "env_dedeuserid"


def test_missing_credential_returns_none(caplog):
    caplog.set_level(logging.ERROR, logger="bili_stalker_mcp.core")

    assert core.get_credential() is None
    assert "SESSDATA is not configured" in caplog.text


def test_invalid_cookie_file_does_not_leak_secret(monkeypatch, tmp_path, caplog):
    secret = "super-secret-cookie-value"
    cookie_file = tmp_path / "cookie.txt"
    cookie_file.write_text(f"not a cookie header {secret}", encoding="utf-8")
    monkeypatch.setenv("BILI_COOKIE_FILE", str(cookie_file))
    caplog.set_level(logging.ERROR, logger="bili_stalker_mcp.core")

    assert core.get_credential() is None

    assert secret not in caplog.text
    assert str(cookie_file) in caplog.text


def test_refresh_token_only_read_from_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSDATA", "env_sessdata")
    monkeypatch.setenv("AC_TIME_VALUE", "env_ac_time_value")
    monkeypatch.setenv("BILI_REFRESH_TOKEN", "env_refresh_token")
    monkeypatch.setenv("BILI_ENABLE_COOKIE_REFRESH", "true")

    assert credentials.load_refresh_token() is None
    cookies_without_file = credentials.load_credential_snapshot().to_credential()
    assert _cookie_values(cookies_without_file)["ac_time_value"] == ""

    token_file = tmp_path / "refresh-token.txt"
    token_file.write_text("file_refresh_token\n", encoding="utf-8")
    monkeypatch.setenv("BILI_REFRESH_TOKEN_FILE", str(token_file))

    snapshot = credentials.load_credential_snapshot()
    cookies_with_file = _cookie_values(snapshot.to_credential())

    assert credentials.load_refresh_token() == "file_refresh_token"
    assert snapshot.refresh_token == "file_refresh_token"
    assert cookies_with_file["ac_time_value"] == "file_refresh_token"


def test_cookie_refresh_switch_defaults_false():
    assert credentials.cookie_refresh_enabled({}) is False
    assert (
        credentials.cookie_refresh_enabled({"BILI_ENABLE_COOKIE_REFRESH": "false"})
        is False
    )
    assert (
        credentials.cookie_refresh_enabled({"BILI_ENABLE_COOKIE_REFRESH": "true"})
        is True
    )


def test_write_refresh_token_file_uses_atomic_replace_and_posix_permissions(
    monkeypatch,
    tmp_path,
):
    target = tmp_path / "refresh-token.txt"
    chmod_calls: list[tuple[Path, int]] = []
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = credentials.os.replace

    def fake_chmod(path, mode):
        chmod_calls.append((Path(path), mode))

    def fake_replace(src, dst):
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(credentials, "_is_posix", lambda: True)
    monkeypatch.setattr(credentials.os, "chmod", fake_chmod)
    monkeypatch.setattr(credentials.os, "replace", fake_replace)

    credentials.write_refresh_token_file(target, "file_refresh_token")

    assert target.read_text(encoding="utf-8") == "file_refresh_token\n"
    assert len(replace_calls) == 1

    tmp_file, replaced_target = replace_calls[0]
    assert replaced_target == target
    assert tmp_file.parent == tmp_path
    assert tmp_file.name.startswith(".refresh-token.txt.")
    assert tmp_file.suffix == ".tmp"
    assert not tmp_file.exists()

    expected_mode = stat.S_IRUSR | stat.S_IWUSR
    assert (tmp_file, expected_mode) in chmod_calls
    assert (target, expected_mode) in chmod_calls
