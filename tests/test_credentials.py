import logging
import os
import stat
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
from filelock import FileLock

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
    "BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS",
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
    assert str(cookie_file) not in caplog.text
    assert "BILI_COOKIE_FILE" in caplog.text


def test_refresh_token_only_read_from_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSDATA", "env_sessdata")
    monkeypatch.setenv("AC_TIME_VALUE", "env_ac_time_value")
    monkeypatch.setenv("BILI_REFRESH_TOKEN", "env_refresh_token")

    assert credentials.load_refresh_token() is None
    cookies_without_file = credentials.load_credential_snapshot().to_credential()
    assert _cookie_values(cookies_without_file)["ac_time_value"] == ""

    monkeypatch.delenv("SESSDATA")
    cookie_file = tmp_path / "cookie.txt"
    _write_cookie_file(cookie_file)
    token_file = tmp_path / "refresh-token.txt"
    token_file.write_text("file_refresh_token\n", encoding="utf-8")
    monkeypatch.setenv("BILI_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("BILI_REFRESH_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("BILI_ENABLE_COOKIE_REFRESH", "true")

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
    fsync_calls: list[int] = []
    original_replace = credentials.os.replace

    def fake_chmod(path, mode):
        chmod_calls.append((Path(path), mode))

    def fake_replace(src, dst):
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    def fake_fsync(fd):
        fsync_calls.append(fd)

    monkeypatch.setattr(credentials, "_is_posix", lambda: True)
    monkeypatch.setattr(credentials.os, "chmod", fake_chmod)
    monkeypatch.setattr(credentials.os, "fsync", fake_fsync)
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
    assert fsync_calls


def test_invalid_refresh_switch_value_does_not_leak_raw_value(caplog):
    secret = "mistaken-secret-in-boolean"
    caplog.set_level(logging.WARNING, logger="bili_stalker_mcp.credentials")

    assert (
        credentials.cookie_refresh_enabled({"BILI_ENABLE_COOKIE_REFRESH": secret})
        is False
    )

    assert "BILI_ENABLE_COOKIE_REFRESH" in caplog.text
    assert secret not in caplog.text


def test_disabled_refresh_file_resolution_has_no_file_io(monkeypatch):
    def unexpected_io(*args, **kwargs):
        raise AssertionError("disabled refresh must not touch files")

    monkeypatch.setattr(credentials, "load_credential_snapshot", unexpected_io)
    assert (
        credentials.resolve_cookie_refresh_files(
            {
                "BILI_ENABLE_COOKIE_REFRESH": "false",
                "BILI_COOKIE_FILE": "missing-cookie",
                "BILI_REFRESH_TOKEN_FILE": "missing-token",
            }
        )
        is None
    )


@pytest.mark.parametrize("env_name", ["SESSDATA", "BILI_JCT", "DEDEUSERID"])
def test_enabled_refresh_rejects_rotating_environment_overrides(
    env_name,
    tmp_path,
):
    secret = "environment-override-secret"
    cookie_file = tmp_path / "cookie.txt"
    token_file = tmp_path / "refresh-token.txt"
    _write_cookie_file(cookie_file)
    token_file.write_text("file-refresh-token\n", encoding="utf-8")
    env = {
        "BILI_ENABLE_COOKIE_REFRESH": "true",
        "BILI_COOKIE_FILE": str(cookie_file),
        "BILI_REFRESH_TOKEN_FILE": str(token_file),
        env_name: secret,
    }

    with pytest.raises(credentials.CredentialLoadError) as exc_info:
        credentials.resolve_cookie_refresh_files(env)

    message = str(exc_info.value)
    assert env_name in message
    assert secret not in message
    assert str(cookie_file) not in message
    assert str(token_file) not in message


def test_enabled_refresh_requires_safe_complete_file_configuration(tmp_path):
    with pytest.raises(credentials.CredentialLoadError) as exc_info:
        credentials.resolve_cookie_refresh_files({"BILI_ENABLE_COOKIE_REFRESH": "true"})
    assert "BILI_COOKIE_FILE" in str(exc_info.value)
    assert "BILI_REFRESH_TOKEN_FILE" in str(exc_info.value)

    cookie_file = tmp_path / "cookie.txt"
    token_file = tmp_path / "refresh-token.txt"
    cookie_file.write_text("SESSDATA=file-session\n", encoding="utf-8")
    token_file.write_text("file-refresh-token\n", encoding="utf-8")
    env = {
        "BILI_ENABLE_COOKIE_REFRESH": "true",
        "BILI_COOKIE_FILE": str(cookie_file),
        "BILI_REFRESH_TOKEN_FILE": str(token_file),
    }
    with pytest.raises(credentials.CredentialLoadError) as exc_info:
        credentials.resolve_cookie_refresh_files(env)
    assert "BILI_JCT" in str(exc_info.value)
    assert "file-session" not in str(exc_info.value)


@pytest.mark.parametrize("target_env", ["BILI_COOKIE_FILE", "BILI_REFRESH_TOKEN_FILE"])
def test_enabled_refresh_rejects_lock_file_as_credential_target(tmp_path, target_env):
    env = {
        "BILI_ENABLE_COOKIE_REFRESH": "true",
        "BILI_COOKIE_FILE": str(tmp_path / "cookie.txt"),
        "BILI_REFRESH_TOKEN_FILE": str(tmp_path / "refresh-token.txt"),
    }
    env[target_env] = str(tmp_path / credentials.COOKIE_REFRESH_LOCK_FILE)

    with pytest.raises(
        credentials.CredentialPersistenceError, match="reserved refresh state"
    ):
        credentials.resolve_cookie_refresh_file_paths(env)


def test_write_cookie_file_is_atomic_and_excludes_refresh_token(
    monkeypatch,
    tmp_path,
):
    target = tmp_path / "cookie.txt"
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = credentials.os.replace
    secret = "must-not-enter-cookie-file"

    def fake_replace(src, dst):
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(credentials.os, "replace", fake_replace)
    credentials.write_cookie_file(
        target,
        {
            "SESSDATA": "new-session",
            "bili_jct": "new-jct",
            "buvid3": "new-buvid3",
            "ac_time_value": secret,
            "refresh_token": secret,
        },
    )

    text = target.read_text(encoding="utf-8")
    assert secret not in text
    assert "refresh" not in text.lower()
    assert credentials.parse_cookie_text(text) == {
        "sessdata": "new-session",
        "bili_jct": "new-jct",
        "buvid3": "new-buvid3",
    }
    assert len(replace_calls) == 1
    tmp_file, replaced_target = replace_calls[0]
    assert replaced_target == target
    assert tmp_file.parent == tmp_path
    assert not tmp_file.exists()


def _new_cookie_values() -> dict[str, str]:
    return {
        "SESSDATA": "new-session-secret",
        "bili_jct": "new-jct-secret",
        "buvid3": "new-buvid3",
        "buvid4": "new-buvid4",
        "DedeUserID": "new-user-id",
        "ac_time_value": "new-refresh-token-secret",
    }


def _credential_artifact(tmp_path: Path, name: str) -> Path:
    return tmp_path / name


def _prepare_old_credential_files(tmp_path: Path) -> tuple[Path, Path]:
    cookie_file = tmp_path / "cookie.txt"
    token_file = tmp_path / "refresh-token.txt"
    _write_cookie_file(
        cookie_file,
        sessdata="old-session-secret",
        bili_jct="old-jct-secret",
    )
    token_file.write_text("old-refresh-token-secret\n", encoding="utf-8")
    return cookie_file, token_file


def _persist_new_credentials(cookie_file: Path, token_file: Path) -> None:
    credentials.persist_refreshed_credentials(
        cookie_file,
        token_file,
        _new_cookie_values(),
        "new-refresh-token-secret",
        "old-refresh-token-secret",
    )


def test_persist_refreshed_credentials_keeps_pending_until_removed(tmp_path):
    cookie_file, token_file = _prepare_old_credential_files(tmp_path)

    _persist_new_credentials(cookie_file, token_file)

    cookie_text = cookie_file.read_text(encoding="utf-8")
    assert "new-session-secret" in cookie_text
    assert "new-refresh-token-secret" not in cookie_text
    assert "old-refresh-token-secret" not in cookie_text
    assert token_file.read_text(encoding="utf-8") == "new-refresh-token-secret\n"
    marker = _credential_artifact(
        tmp_path, credentials.COOKIE_REFRESH_TRANSACTION_MARKER
    )
    assert not marker.exists()

    pending = credentials.read_pending_confirmation(token_file)
    assert pending is not None
    assert pending.old_refresh_token == "old-refresh-token-secret"
    assert pending.new_refresh_token == "new-refresh-token-secret"
    assert "old-refresh-token-secret" not in repr(pending)
    assert "new-refresh-token-secret" not in repr(pending)

    credentials.remove_pending_confirmation(token_file)
    assert credentials.read_pending_confirmation(token_file) is None


class _SimulatedCrash(BaseException):
    pass


def test_recovery_discards_staged_group_when_crash_precedes_pending(
    monkeypatch,
    tmp_path,
):
    cookie_file, token_file = _prepare_old_credential_files(tmp_path)

    def crash_before_pending(*args, **kwargs):
        raise _SimulatedCrash

    monkeypatch.setattr(
        credentials, "_write_pending_confirmation", crash_before_pending
    )
    with pytest.raises(_SimulatedCrash):
        _persist_new_credentials(cookie_file, token_file)

    marker = _credential_artifact(
        tmp_path, credentials.COOKIE_REFRESH_TRANSACTION_MARKER
    )
    marker_text = marker.read_text(encoding="utf-8")
    for secret in (
        "old-session-secret",
        "old-jct-secret",
        "new-session-secret",
        "new-jct-secret",
        "old-refresh-token-secret",
        "new-refresh-token-secret",
    ):
        assert secret not in marker_text
    assert '"state":"prepared"' in marker_text

    credentials.recover_credential_transaction(cookie_file, token_file)

    assert "old-session-secret" in cookie_file.read_text(encoding="utf-8")
    assert token_file.read_text(encoding="utf-8") == "old-refresh-token-secret\n"
    assert not marker.exists()
    assert credentials.read_pending_confirmation(token_file) is None


def test_recovery_rolls_forward_when_crash_follows_pending(
    monkeypatch,
    tmp_path,
):
    cookie_file, token_file = _prepare_old_credential_files(tmp_path)
    original_commit = credentials._commit_staged_credentials

    def crash_before_commit(*args, **kwargs):
        raise _SimulatedCrash

    monkeypatch.setattr(credentials, "_commit_staged_credentials", crash_before_commit)
    with pytest.raises(_SimulatedCrash):
        _persist_new_credentials(cookie_file, token_file)
    monkeypatch.setattr(credentials, "_commit_staged_credentials", original_commit)

    assert "old-session-secret" in cookie_file.read_text(encoding="utf-8")
    assert token_file.read_text(encoding="utf-8") == "old-refresh-token-secret\n"
    assert credentials.read_pending_confirmation(token_file) is not None

    credentials.recover_credential_transaction(cookie_file, token_file)

    assert "new-session-secret" in cookie_file.read_text(encoding="utf-8")
    assert token_file.read_text(encoding="utf-8") == "new-refresh-token-secret\n"
    assert credentials.read_pending_confirmation(token_file) is not None


def test_snapshot_load_recovers_after_first_target_replace(
    monkeypatch,
    tmp_path,
):
    cookie_file, token_file = _prepare_old_credential_files(tmp_path)
    original_replace = credentials.os.replace

    def crash_after_cookie_replace(src, dst):
        original_replace(src, dst)
        if (
            Path(src).name == credentials.COOKIE_REFRESH_COOKIE_STAGE
            and Path(dst) == cookie_file
        ):
            raise _SimulatedCrash

    monkeypatch.setattr(credentials.os, "replace", crash_after_cookie_replace)
    with pytest.raises(_SimulatedCrash):
        _persist_new_credentials(cookie_file, token_file)
    monkeypatch.setattr(credentials.os, "replace", original_replace)

    assert "new-session-secret" in cookie_file.read_text(encoding="utf-8")
    assert token_file.read_text(encoding="utf-8") == "old-refresh-token-secret\n"

    snapshot = credentials.load_credential_snapshot(
        {
            "BILI_ENABLE_COOKIE_REFRESH": "true",
            "BILI_COOKIE_FILE": str(cookie_file),
            "BILI_REFRESH_TOKEN_FILE": str(token_file),
        }
    )

    assert snapshot.sessdata == "new-session-secret"
    assert snapshot.refresh_token == "new-refresh-token-secret"
    assert token_file.read_text(encoding="utf-8") == "new-refresh-token-secret\n"


def test_recovery_clears_marker_left_after_both_replacements(
    monkeypatch,
    tmp_path,
):
    cookie_file, token_file = _prepare_old_credential_files(tmp_path)
    original_unlink = credentials._unlink_state_file

    def crash_before_marker_removal(path):
        if Path(path).name == credentials.COOKIE_REFRESH_TRANSACTION_MARKER:
            raise _SimulatedCrash
        original_unlink(path)

    monkeypatch.setattr(credentials, "_unlink_state_file", crash_before_marker_removal)
    with pytest.raises(_SimulatedCrash):
        _persist_new_credentials(cookie_file, token_file)
    monkeypatch.setattr(credentials, "_unlink_state_file", original_unlink)

    assert "new-session-secret" in cookie_file.read_text(encoding="utf-8")
    assert token_file.read_text(encoding="utf-8") == "new-refresh-token-secret\n"
    marker = _credential_artifact(
        tmp_path, credentials.COOKIE_REFRESH_TRANSACTION_MARKER
    )
    assert marker.exists()

    credentials.recover_credential_transaction(cookie_file, token_file)

    assert not marker.exists()
    assert credentials.read_pending_confirmation(token_file) is not None


def test_persistence_failure_before_pending_keeps_old_group_and_redacts_errors(
    monkeypatch,
    tmp_path,
):
    cookie_file, token_file = _prepare_old_credential_files(tmp_path)

    def fail_marker(*args, **kwargs):
        raise OSError("new-session-secret new-refresh-token-secret")

    monkeypatch.setattr(credentials, "_write_transaction_marker", fail_marker)
    with pytest.raises(credentials.CredentialPersistenceError) as exc_info:
        _persist_new_credentials(cookie_file, token_file)

    assert "old-session-secret" in cookie_file.read_text(encoding="utf-8")
    assert token_file.read_text(encoding="utf-8") == "old-refresh-token-secret\n"
    assert credentials.read_pending_confirmation(token_file) is None
    message = str(exc_info.value)
    assert "new-session-secret" not in message
    assert "new-refresh-token-secret" not in message


def test_transaction_files_use_owner_only_permissions_best_effort(
    monkeypatch,
    tmp_path,
):
    cookie_file, token_file = _prepare_old_credential_files(tmp_path)
    chmod_calls: list[tuple[Path, int]] = []

    def fake_chmod(path, mode):
        chmod_calls.append((Path(path), mode))

    monkeypatch.setattr(credentials, "_is_posix", lambda: True)
    monkeypatch.setattr(credentials.os, "chmod", fake_chmod)
    _persist_new_credentials(cookie_file, token_file)

    protected_names = {path.name for path, _mode in chmod_calls}
    assert credentials.COOKIE_REFRESH_COOKIE_STAGE in protected_names
    assert credentials.COOKIE_REFRESH_TOKEN_STAGE in protected_names
    assert credentials.COOKIE_REFRESH_TRANSACTION_MARKER in protected_names
    assert credentials.COOKIE_REFRESH_PENDING_CONFIRM in protected_names
    assert cookie_file.name in protected_names
    assert token_file.name in protected_names
    assert all(mode == stat.S_IRUSR | stat.S_IWUSR for _path, mode in chmod_calls)


def test_enabled_snapshot_waits_for_cross_process_lock(tmp_path):
    cookie_file, token_file = _prepare_old_credential_files(tmp_path)
    files = credentials.CookieRefreshFiles(cookie_file, token_file)
    ready_file = tmp_path / "child-ready"
    done_file = tmp_path / "child-done"
    child_env = os.environ.copy()
    child_env.update(
        {
            "BILI_ENABLE_COOKIE_REFRESH": "true",
            "BILI_COOKIE_FILE": str(cookie_file),
            "BILI_REFRESH_TOKEN_FILE": str(token_file),
            "TEST_READY_FILE": str(ready_file),
            "TEST_DONE_FILE": str(done_file),
        }
    )
    script = (
        "import os; from pathlib import Path; "
        "from bili_stalker_mcp import credentials; "
        "Path(os.environ['TEST_READY_FILE']).write_text('ready', encoding='utf-8'); "
        "credentials.load_credential_snapshot(); "
        "Path(os.environ['TEST_DONE_FILE']).write_text('done', encoding='utf-8')"
    )
    process = None
    try:
        with FileLock(str(files.lock_path)):
            process = subprocess.Popen(
                [sys.executable, "-c", script],
                cwd=Path(__file__).parents[1],
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + 10
            while not ready_file.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert ready_file.exists()
            assert not done_file.exists()

        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stdout + stderr
        assert done_file.read_text(encoding="utf-8") == "done"
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_refresh_state_files_are_excluded_from_sdist_and_wheel() -> None:
    project_root = Path(__file__).parents[1]
    configuration = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    targets = configuration["tool"]["hatch"]["build"]["targets"]
    required_patterns = {
        "/**/.bili-cookie-refresh-transaction.json",
        "/**/.bili-cookie-refresh-cookie.stage",
        "/**/.bili-cookie-refresh-token.stage",
        "/**/.bili-cookie-refresh-pending.json",
        "/**/.bili-cookie-refresh.lock",
        "/**/.bili-cookie-refresh-*.tmp",
    }

    assert required_patterns <= set(targets["sdist"]["exclude"])
    assert required_patterns <= set(targets["wheel"]["exclude"])
