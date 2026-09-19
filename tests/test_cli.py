import asyncio
import io
import json
import os
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from bili_stalker_mcp import cli, server
from bili_stalker_mcp.errors import RiskControlError
from bili_stalker_mcp.infra import http_client


@pytest.fixture(autouse=True)
def isolated_cli(monkeypatch):
    monkeypatch.setattr(cli, "_configure_logging", lambda: None)
    for name in (
        "SESSDATA",
        "BILI_JCT",
        "BUVID3",
        "BUVID4",
        "DEDEUSERID",
        "BILI_COOKIE_FILE",
        "BILI_REFRESH_TOKEN_FILE",
        "BILI_ENABLE_COOKIE_REFRESH",
    ):
        monkeypatch.delenv(name, raising=False)


class _FakeServer:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.transport: str | None = None

    def run(self, *, transport: str) -> None:
        self.transport = transport
        if self.error is not None:
            raise self.error


@pytest.mark.parametrize("argv", [[], ["serve"]])
def test_main_returns_zero_after_normal_shutdown(monkeypatch, argv):
    fake_server = _FakeServer()
    monkeypatch.setattr(server, "create_server", lambda: fake_server)
    monkeypatch.setattr(cli, "_configure_logging", lambda: None)
    monkeypatch.setattr(cli, "_close_http_client_sync", lambda: None)

    assert cli.main(argv) == 0
    assert fake_server.transport == "stdio"


def test_main_returns_nonzero_when_server_start_fails(monkeypatch):
    fake_server = _FakeServer(error=RuntimeError("startup failed"))
    monkeypatch.setattr(server, "create_server", lambda: fake_server)
    monkeypatch.setattr(cli, "_configure_logging", lambda: None)
    monkeypatch.setattr(cli, "_close_http_client_sync", lambda: None)

    assert cli.main([]) == 1


@pytest.mark.parametrize("argv", [["--help"], ["--version"], ["call", "--help"]])
def test_help_and_version_do_not_load_server(argv):
    script = (
        "import sys; from bili_stalker_mcp.cli import main; "
        f"sys.argv = ['bili-stalker-mcp', *{argv!r}]; "
        "\ntry: main()"
        "\nfinally: assert 'bili_stalker_mcp.server' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
    assert result.stderr == ""


def test_package_entrypoint_outputs_json():
    result = subprocess.run(
        [sys.executable, "-m", "bili_stalker_mcp", "tools"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "BILI_PROXY": ""},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "search_users" in {tool["name"] for tool in json.loads(result.stdout)}


def test_tools_exposes_entire_catalog_and_live_schema(capsys):
    expected = asyncio.run(server.create_server().list_tools())
    assert cli.main(["tools"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert {tool["name"] for tool in catalog} == {tool.name for tool in expected}

    assert cli.main(["tools", "get_video_detail", "--pretty"]) == 0
    schema = json.loads(capsys.readouterr().out)
    video_tool = next(tool for tool in expected if tool.name == "get_video_detail")
    assert schema["inputSchema"] == video_tool.parameters
    assert "ctx" not in schema["inputSchema"]["properties"]


@pytest.mark.parametrize(
    ("tool_name", "arguments", "service_name"),
    [
        ("search_users", {"keyword": "中文用户"}, "search_users_service"),
        ("get_user_info", {"user_id_or_username": "123"}, "fetch_user_info"),
        (
            "get_user_snapshot",
            {
                "user_id_or_username": "123",
                "video_limit": 0,
                "dynamic_limit": 0,
                "article_limit": 0,
            },
            "fetch_user_info",
        ),
        ("get_user_videos", {"user_id_or_username": "123"}, "fetch_user_videos"),
        (
            "search_user_videos",
            {"user_id_or_username": "123", "keyword": "中文关键词"},
            "fetch_user_videos",
        ),
        (
            "get_video_detail",
            {"bvid": "BV1xx411c7mD", "fetch_subtitles": True},
            "fetch_video_detail",
        ),
        (
            "get_user_dynamics",
            {"user_id_or_username": "123", "cursor": None, "dynamic_type": "REVIEW"},
            "fetch_user_dynamics",
        ),
        ("get_user_articles", {"user_id_or_username": "123"}, "fetch_user_articles"),
        (
            "get_article_content",
            {"article_id": "748254891671027745"},
            "fetch_article_content",
        ),
        (
            "get_user_followings",
            {"user_id_or_username": "123"},
            "fetch_user_followings",
        ),
        (
            "get_content_comments",
            {"content_type": "dynamic", "content_id": "748254891671027745"},
            "fetch_content_comments",
        ),
        (
            "get_content_comment_replies",
            {
                "content_type": "video",
                "content_id": "BV1xx411c7mD",
                "root_rpid": 987654321012345678,
            },
            "fetch_content_comment_replies",
        ),
    ],
)
def test_call_routes_all_tools_through_existing_services(
    monkeypatch, capsys, tool_name, arguments, service_name
):
    payload = {"title": "中文内容", "id": "748254891671027745"}
    service = AsyncMock(return_value=payload)
    credential = AsyncMock(return_value=None)
    monkeypatch.setattr(server, service_name, service)
    monkeypatch.setattr(server, "_get_credential_from_context", credential)

    assert cli.main(["call", tool_name, "--args", json.dumps(arguments)]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert "中文内容" in captured.out
    if tool_name == "get_user_snapshot":
        assert result == {
            "uid": 123,
            "user": payload,
            "videos": None,
            "dynamics": None,
            "articles": None,
            "errors": {},
        }
    else:
        assert result == payload
    service.assert_awaited_once()
    if tool_name != "search_users":
        credential.assert_awaited_once()
        assert credential.await_args.args[0] is not None
    if tool_name == "get_video_detail":
        assert service.await_args.kwargs["fetch_subtitles"] is True
        assert service.await_args.kwargs["subtitle_mode"] == "smart"
    if tool_name == "get_content_comment_replies":
        assert service.await_args.kwargs["root_rpid"] == 987654321012345678
    assert captured.err == ""


@pytest.mark.parametrize("source", ["file", "stdin"])
def test_arguments_accept_utf8_bom_files_and_stdin(
    monkeypatch, tmp_path, capsys, source
):
    raw = '\ufeff{"keyword": "中文用户", "limit": 3}'
    service = AsyncMock(return_value={"users": []})
    monkeypatch.setattr(server, "search_users_service", service)
    if source == "file":
        path = tmp_path / "参数.json"
        path.write_text(raw, encoding="utf-8")
        source_path = str(path)
    else:
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        source_path = "-"

    assert cli.main(["call", "search_users", "--args-file", source_path]) == 0
    service.assert_awaited_once_with("中文用户", 3)
    assert json.loads(capsys.readouterr().out) == {"users": []}


@pytest.mark.parametrize("raw", ["{", "[]", "null", '"text"', "1"])
def test_malformed_or_nonobject_arguments_do_not_start_server(monkeypatch, capsys, raw):
    monkeypatch.setattr(server, "create_server", lambda: pytest.fail("server started"))
    assert cli.main(["call", "search_users", "--args", raw]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["reason"] == "invalid_arguments"


def test_missing_argument_file_is_a_usage_error(tmp_path, capsys):
    assert (
        cli.main(
            ["call", "search_users", "--args-file", str(tmp_path / "missing.json")]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["reason"] == "invalid_arguments"


@pytest.mark.parametrize("command", ["tools", "call"])
def test_unknown_tool_returns_usage_error(capsys, command):
    assert cli.main([command, "not_a_tool"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Unknown tool" in json.loads(captured.err)["error"]["message"]


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"keyword": ""},
        {"keyword": "demo", "limit": 21},
        {"keyword": "demo", "typo": 1},
    ],
)
def test_schema_validation_happens_before_upstream(monkeypatch, capsys, arguments):
    service = AsyncMock()
    monkeypatch.setattr(server, "search_users_service", service)
    assert cli.main(["call", "search_users", "--args", json.dumps(arguments)]) == 2
    service.assert_not_awaited()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["reason"] == "invalid_arguments"


def test_missing_credentials_return_failure_without_upstream(monkeypatch, capsys):
    service = AsyncMock()
    monkeypatch.setattr(server, "fetch_user_info", service)
    assert (
        cli.main(["call", "get_user_info", "--args", '{"user_id_or_username":"123"}'])
        == 1
    )
    service.assert_not_awaited()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Missing SESSDATA" in json.loads(captured.err)["error"]["message"]


def test_cli_uses_existing_refresh_path(monkeypatch, capsys):
    refresh = AsyncMock(return_value=None)
    service = AsyncMock(return_value={"mid": 123})
    monkeypatch.setattr(server, "cookie_refresh_enabled", lambda: True)
    monkeypatch.setattr(server, "load_refreshing_credential", refresh)
    monkeypatch.setattr(server, "fetch_user_info", service)
    assert (
        cli.main(["call", "get_user_info", "--args", '{"user_id_or_username":"123"}'])
        == 0
    )
    refresh.assert_awaited_once()
    assert json.loads(capsys.readouterr().out) == {"mid": 123}


@pytest.mark.parametrize("failure", [False, True])
def test_request_cleanup_runs_on_same_loop_on_success_and_failure(
    monkeypatch, capsys, failure
):
    loops = []

    async def search(*_args):
        loops.append(asyncio.get_running_loop())
        if failure:
            raise RiskControlError(retry_after=300)
        return {"users": []}

    async def close():
        loops.append(asyncio.get_running_loop())

    monkeypatch.setattr(server, "search_users_service", search)
    monkeypatch.setattr(http_client, "close_shared_http_client", close)
    assert cli.main(["call", "search_users", "--args", '{"keyword":"demo"}']) == (
        1 if failure else 0
    )
    assert len(loops) == 2
    assert loops[0] is loops[1]
    captured = capsys.readouterr()
    if failure:
        assert captured.out == ""
        error = json.loads(captured.err)["error"]
        assert error["code"] == 412
        assert error["reason"] == "risk_control"
        assert error["retry_after"] == 300


def test_unexpected_error_is_sanitized(monkeypatch, capsys):
    async def fail(*_args):
        raise RuntimeError("private-cookie-value")

    monkeypatch.setattr(server, "search_users_service", fail)
    assert cli.main(["call", "search_users", "--args", '{"keyword":"demo"}']) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private-cookie-value" not in captured.err
    assert json.loads(captured.err)["error"]["reason"] == "internal_error"
