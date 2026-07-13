import json
import tomllib
from pathlib import Path

import pytest

from bili_stalker_mcp import setup_cookie_refresh as setup


def test_create_credential_files_writes_supported_values_only(tmp_path):
    secret = "refresh-token-test-secret"

    env = setup.create_credential_files(
        tmp_path / "secrets",
        "Cookie: SESSDATA=test-sess; bili_jct=test-jct; sid=ignored; DedeUserID=1",
        secret,
    )

    cookie_path = Path(env["BILI_COOKIE_FILE"])
    token_path = Path(env["BILI_REFRESH_TOKEN_FILE"])
    cookie_text = cookie_path.read_text(encoding="utf-8")

    assert "SESSDATA=test-sess" in cookie_text
    assert "bili_jct=test-jct" in cookie_text
    assert "DedeUserID=1" in cookie_text
    assert "sid=" not in cookie_text
    assert secret not in cookie_text
    assert token_path.read_text(encoding="utf-8") == f"{secret}\n"
    assert secret not in json.dumps(env)


def test_create_credential_files_rejects_missing_required_cookie(tmp_path):
    with pytest.raises(setup.SetupError, match="SESSDATA"):
        setup.create_credential_files(
            tmp_path / "secrets",
            "bili_jct=test-jct",
            "refresh-token-test-secret",
        )


def test_create_credential_files_never_overwrites_existing_files(tmp_path):
    target = tmp_path / "secrets"
    target.mkdir()
    cookie_path = target / setup.COOKIE_FILE_NAME
    cookie_path.write_text("existing", encoding="utf-8")

    with pytest.raises(setup.SetupError, match="Refusing to overwrite"):
        setup.create_credential_files(
            target,
            "SESSDATA=test-sess; bili_jct=test-jct",
            "refresh-token-test-secret",
        )

    assert cookie_path.read_text(encoding="utf-8") == "existing"


def test_create_credential_files_removes_new_cookie_if_token_write_fails(
    monkeypatch, tmp_path
):
    def fail_token_write(*_args, **_kwargs):
        raise setup.CredentialLoadError("safe failure")

    monkeypatch.setattr(setup, "write_refresh_token_file", fail_token_write)
    directory = tmp_path / "secrets"

    with pytest.raises(setup.SetupError, match="Unable to create"):
        setup.create_credential_files(
            directory,
            "SESSDATA=test-sess; bili_jct=test-jct",
            "refresh-token-test-secret",
        )

    assert not (directory / setup.COOKIE_FILE_NAME).exists()


def test_create_credential_files_rejects_a_repository_directory():
    project_root = Path(__file__).parents[1]

    with pytest.raises(setup.SetupError, match="outside this repository"):
        setup.create_credential_files(
            project_root / "not-secret-output",
            "SESSDATA=test-sess; bili_jct=test-jct",
            "refresh-token-test-secret",
        )


def test_packaged_console_entrypoint_targets_setup_module():
    project_root = Path(__file__).parents[1]
    configuration = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert configuration["project"]["scripts"]["bili-stalker-cookie-setup"] == (
        "bili_stalker_mcp.setup_cookie_refresh:main"
    )
