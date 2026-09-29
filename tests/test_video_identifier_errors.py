import json
from unittest.mock import AsyncMock

import httpx
import pytest
from bilibili_api import Credential

from bili_stalker_mcp import cli, server
from bili_stalker_mcp.utils import video_id_parser


@pytest.mark.parametrize(
    "tool,arguments,service_name",
    [
        ("get_video_detail", {"fetch_subtitles": False}, "fetch_video_detail"),
        ("get_video_detail", {"fetch_subtitles": True}, "fetch_video_detail"),
        ("get_content_comments", {"content_type": "video"}, "fetch_content_comments"),
        (
            "get_content_comment_replies",
            {"content_type": "video", "root_rpid": 123},
            "fetch_content_comment_replies",
        ),
    ],
)
@pytest.mark.parametrize(
    "raw,reason",
    [
        ("invalid-video", "invalid_video_identifier"),
        ("https://b23.tv/private-token", "short_link_resolution_failed"),
    ],
)
def test_cli_rejects_bad_video_before_service(
    monkeypatch, capsys, tool, arguments, service_name, raw, reason
):
    monkeypatch.setattr(cli, "_configure_logging", lambda: None)
    monkeypatch.setattr(
        server,
        "_get_credential_from_context",
        AsyncMock(return_value=Credential(sessdata="test")),
    )
    monkeypatch.setattr(server, "validate_cookie_refresh_runtime", lambda: None)
    service = AsyncMock()
    monkeypatch.setattr(server, service_name, service)
    head = AsyncMock(side_effect=httpx.ReadTimeout("private transport details"))
    client = type("Client", (), {"head": head})()
    monkeypatch.setattr(video_id_parser, "get_shared_http_client", lambda: client)
    key = "bvid" if tool == "get_video_detail" else "content_id"
    arguments = {**arguments, key: raw}
    assert cli.main(["call", tool, "--args", json.dumps(arguments)]) == 1
    service.assert_not_awaited()
    output = capsys.readouterr()
    assert output.out == ""
    error = json.loads(output.err)["error"]
    assert error["reason"] == reason
    assert error["request_id"]
    assert "private" not in output.err
    assert error["code"] is None
    assert head.await_count == (1 if raw.startswith("https:") else 0)
