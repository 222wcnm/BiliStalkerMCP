"""Exercise the installed native CLI against a real stdio subprocess."""

import json
import os
import subprocess
import sys

import pytest


@pytest.fixture
def clean_env():
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("BILI_")
        and k not in {"SESSDATA", "BUVID3", "BUVID4", "DEDEUSERID"}
    }
    env.update(
        PYTHONUTF8="1",
        BILI_ENABLE_COOKIE_REFRESH="false",
        BILI_LOG_LEVEL="ERROR",
        FASTMCP_LOG_LEVEL="ERROR",
        FASTMCP_SHOW_SERVER_BANNER="false",
    )
    return env


def test_discovery_is_offline(clean_env):
    script = """
import asyncio, socket
from unittest.mock import patch

def forbidden(*args, **kwargs):
    raise AssertionError('discovery touched runtime')
socket.create_connection = forbidden
from bili_stalker_mcp import server
with patch('bili_stalker_mcp.cookie_refresh._assert_sdk_compatibility', forbidden), patch('bili_stalker_mcp.credentials.load_credential_snapshot', forbidden), patch('bili_stalker_mcp.infra.http_client.SharedRawHttpClient', forbidden):
    assert len(asyncio.run(server.create_server().list_tools())) == 12
"""
    env = dict(
        clean_env,
        BILI_PROXY="http://127.0.0.1:9",
        BILI_ENABLE_COOKIE_REFRESH="true",
        BILI_COOKIE_FILE="missing-cookie.txt",
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
    )
    assert result.returncode == 0, result.stderr


def test_direct_core_call_initializes_sdk_before_request(clean_env):
    script = """
import asyncio
from unittest.mock import patch
from bilibili_api import request_settings
from bili_stalker_mcp import config, core

assert not config._request_settings_initialized
proxy = 'http://127.0.0.1:9'
async def search(**kwargs):
    assert request_settings.get_proxy() == proxy
    assert request_settings.get_timeout() == config.REQUEST_TIMEOUT
    return {'result': [{'mid': 123, 'uname': 'target'}]}

with patch.object(config, '_proxy_reachable', return_value=True) as probe:
    with patch('bili_stalker_mcp.services.user_service.search.search_by_type', search):
        result = asyncio.run(core.search_users('target'))
    assert result['exact_match_uid'] == 123
    probe.assert_called_once_with(proxy)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=dict(clean_env, BILI_PROXY="http://127.0.0.1:9"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("keyword,exit_code", [("中文 用户", 0), ("risk", 1)])
def test_native_stdio_result(tmp_path, clean_env, keyword, exit_code):
    script = """
from bili_stalker_mcp import server, cli
from bili_stalker_mcp.errors import RiskControlError
async def search(keyword, limit=10):
    assert isinstance(limit, int)
    if keyword == 'risk':
        raise RiskControlError(retry_after=300)
    return {'users': [{'uid': 123, 'name': keyword, 'is_exact_match': True}], 'count': 1, 'exact_match_uid': 123}
server.search_users_service = search
raise SystemExit(cli.main(['serve']))
"""
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "bili": {
                        "command": sys.executable,
                        "args": ["-c", script],
                        "cwd": os.getcwd(),
                        "env": {
                            k: v
                            for k, v in clean_env.items()
                            if k.startswith(("BILI_", "FASTMCP_", "PYTHON"))
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from fastmcp.cli import app; app()",
            "call",
            str(config),
            "search_users",
            f"keyword={keyword}",
            "limit=1",
            "--json",
        ],
        env=clean_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == exit_code, result.stderr
    payload = json.loads(result.stdout)
    assert payload["is_error"] == bool(exit_code)
    if exit_code:
        error = json.loads(payload["content"][0]["text"])
        assert error["reason"] == "risk_control"
        assert error["retry_after"] == 300
        assert error["request_id"]
    else:
        assert payload["structured_content"]["users"][0]["name"] == keyword
