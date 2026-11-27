import json
from collections import Counter
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client
from fastmcp.cli.client import parse_tool_arguments
from jsonschema import validate

from bili_stalker_mcp import cli, server
from bili_stalker_mcp.models import VideoDetailResponse
from bili_stalker_mcp.services import subtitle_output, subtitle_service, user_service

BVID = "BV1xx411c7mD"


@pytest.fixture
def tracks(monkeypatch):
    user_service._fetch_video_detail_cached.cache_clear()
    user_service._fetch_video_metadata_cached.cache_clear()
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MODE", "never")
    monkeypatch.setattr(
        server, "_get_credential_from_context", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(cli, "_configure_logging", lambda: None)

    pages = [
        {"cid": 101, "page": 1, "part": "Long video", "duration": 900},
        {"cid": 202, "page": 2, "part": "Outro", "duration": 20},
    ]
    bodies = {
        "101-zh": [
            {"from": 240.25, "to": 242, "content": " 开头\n第二行 "},
            {"from": 251, "to": 252, "content": "同窗"},
            {"from": 300, "to": 302, "content": "中段"},
            {"from": 701, "to": 705, "content": "后段"},
            {"content": "无时间"},
        ],
        "101-en": [{"from": 242, "to": 243, "content": "Translation"}],
        "202-zh": [
            {"from": 0, "to": 1, "content": "P2 start"},
            {"from": 2, "to": 3, "content": "P2 end"},
        ],
    }
    languages = {"zh": "zh-CN", "en": "en-US"}
    calls = Counter()

    class FakeVideo:
        def __init__(self, bvid, credential):
            assert bvid == BVID

        async def get_info(self):
            return {"bvid": BVID, "pages": pages}

        async def get_player_info(self, cid):
            subtitles = [
                {
                    "lan": languages[name.split("-")[1]],
                    "subtitle_url": f"https://example.com/{name}",
                }
                for name in bodies
                if name.startswith(f"{cid}-")
            ]
            return {"subtitle": {"subtitles": subtitles}}

    async def get_json(url, *, cred):
        name = url.rsplit("/", 1)[-1]
        calls[name] += 1
        return {"body": bodies[name]}

    monkeypatch.setattr(user_service.video, "Video", FakeVideo)
    monkeypatch.setattr(subtitle_service, "get_json", get_json)
    yield calls
    user_service._fetch_video_detail_cached.cache_clear()
    user_service._fetch_video_metadata_cached.cache_clear()


async def _subtitles(**options):
    result = await user_service.fetch_video_detail(BVID, True, **options)
    validate(result, VideoDetailResponse.model_json_schema())
    return result["subtitles"]


@pytest.mark.asyncio
async def test_anchors_match_full_text_across_pages_and_languages(tracks):
    selection = {"subtitle_mode": "full", "subtitle_scope": "all"}
    timed = await _subtitles(subtitle_format="anchors", **selection)
    assert tracks == {"101-zh": 1, "101-en": 1, "202-zh": 1}
    default = await _subtitles(**selection)
    assert timed["full_text"] == default["full_text"]
    assert timed["returned_chars"] == len(default["full_text"])
    assert timed["scope"]["returned_pages"] == [1, 2]
    assert not timed["truncated"]
    assert default["errors"] == []
    assert all(
        "anchors" not in track and "coverage" not in track
        for track in default["tracks"]
    )
    assert len(timed["errors"]) == 1 and "invalid timestamps" in timed["errors"][0]

    lines = timed["full_text"].split("\n")
    assert "无时间" in lines
    first, translation, second = timed["tracks"]
    assert [(lines[line - 1], start) for line, start in first["anchors"]] == [
        ("开头", 240.25),
        ("中段", 300),
        ("后段", 701),
    ]
    assert [(lines[line - 1], start) for line, start in translation["anchors"]] == [
        ("Translation", 242),
    ]
    assert [(lines[line - 1], start) for line, start in second["anchors"]] == [
        ("P2 start", 0),
        ("P2 end", 2),
    ]
    assert first["coverage"] == {
        "source_start_sec": 240.25,
        "source_end_sec": 705,
        "returned_start_sec": 240.25,
        "returned_end_sec": 705,
        "returned_cues": 5,
    }


@pytest.mark.asyncio
async def test_line_sampling_and_cache_separate_intervals(tracks):
    sampled = await _subtitles(
        subtitle_format="anchors", subtitle_anchor_interval_lines=2
    )
    anchors = sampled["tracks"][0]["anchors"]
    assert anchors == [[1, 240.25], [3, 251], [5, 701]]
    anchors.clear()
    cached = await _subtitles(
        subtitle_format="anchors", subtitle_anchor_interval_lines=2
    )
    assert cached["tracks"][0]["anchors"] == [[1, 240.25], [3, 251], [5, 701]]
    timed = await _subtitles(subtitle_format="anchors", subtitle_anchor_interval_sec=60)
    assert timed["tracks"][0]["anchors"] == [[1, 240.25], [4, 300], [5, 701]]
    assert tracks == {"101-zh": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tail,last", [("", [[1, 240.25]]), ("同", [[1, 240.25], [3, 251]])]
)
async def test_anchors_follow_actual_text_when_budget_cuts_a_cue(tracks, tail, last):
    text = "开头\n第二行\n" + tail
    subtitles = await _subtitles(
        subtitle_format="anchors", subtitle_max_chars=len(text)
    )
    assert subtitles["full_text"] == text
    assert subtitles["truncated"]
    track = subtitles["tracks"][0]
    assert track["anchors"] == last
    assert track["coverage"]["source_end_sec"] == 705
    assert track["coverage"]["returned_end_sec"] == (252 if tail else 242)
    assert track["coverage"]["returned_cues"] == len(last)


@pytest.mark.asyncio
async def test_anchor_limit_preserves_endpoints_and_text(tracks, monkeypatch):
    monkeypatch.setattr(subtitle_output, "MAX_SUBTITLE_ANCHORS", 5)
    subtitles = await _subtitles(
        subtitle_format="anchors", subtitle_mode="full", subtitle_scope="all"
    )
    first, translation, second = subtitles["tracks"]
    assert first["anchors_truncated"]
    assert [start for _, start in first["anchors"]] == [240.25, 701]
    assert "anchors_truncated" not in translation
    assert "anchors_truncated" not in second
    assert sum(len(track["anchors"]) for track in subtitles["tracks"]) == 5
    assert "中段" in subtitles["full_text"]
    assert not subtitles["truncated"]


@pytest.mark.asyncio
@pytest.mark.parametrize("budget_kind", ["characters", "segments"])
async def test_segment_budget_stops_at_complete_cue_across_tracks(
    tracks, monkeypatch, budget_kind
):
    budget = 7 if budget_kind == "characters" else 12000
    if budget_kind == "segments":
        monkeypatch.setattr(subtitle_output, "MAX_SUBTITLE_SEGMENTS", 1)
    subtitles = await _subtitles(
        subtitle_mode="full",
        subtitle_scope="all",
        subtitle_format="segments",
        subtitle_max_chars=budget,
    )
    assert subtitles["full_text"] == ""
    assert subtitles["truncated"]
    assert subtitles["returned_chars"] == len("开头\n第二行")
    assert subtitles["scope"]["returned_pages"] == [1]
    first, translation, second = subtitles["tracks"]
    assert first["segments"] == [
        {"start_sec": 240.25, "end_sec": 242, "text": "开头\n第二行"},
    ]
    assert first["coverage"]["source_end_sec"] == 705
    assert first["coverage"]["returned_end_sec"] == 242
    assert translation["segments"] == second["segments"] == []
    assert second["coverage"]["returned_start_sec"] is None


@pytest.mark.asyncio
async def test_mcp_exact_window_keeps_source_times_and_excludes_touching_cues(tracks):
    async with Client(server.create_server()) as client:
        tool = next(
            tool
            for tool in await client.list_tools()
            if tool.name == "get_video_detail"
        )
        args = (f"bvid={BVID}", "fetch_subtitles=true", "subtitle_format=segments")
        first = await client.call_tool(
            "get_video_detail",
            parse_tool_arguments(
                (*args, "subtitle_start_sec=242", "subtitle_end_sec=300"),
                None,
                tool.input_schema,
            ),
        )
        second = await client.call_tool(
            "get_video_detail",
            parse_tool_arguments(
                (*args, "subtitle_start_sec=702.5", "subtitle_end_sec=703"),
                None,
                tool.input_schema,
            ),
        )
    early = first.structured_content["subtitles"]
    late = second.structured_content["subtitles"]
    assert early["tracks"][0]["segments"] == [
        {"start_sec": 251, "end_sec": 252, "text": "同窗"},
    ]
    assert late["tracks"][0]["segments"] == [
        {"start_sec": 701, "end_sec": 705, "text": "后段"},
    ]
    assert late["tracks"][0]["coverage"]["source_start_sec"] == 240.25
    assert late["tracks"][0]["coverage"]["returned_start_sec"] == 701
    assert late["scope"]["returned_pages"] == [1]
    assert not late["truncated"]
    assert tracks == {"101-zh": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "format_name,option",
    [
        ("anchors", "subtitle_anchor_interval_sec"),
        ("anchors", "subtitle_anchor_interval_lines"),
        ("segments", "subtitle_start_sec"),
        ("segments", "subtitle_end_sec"),
    ],
)
async def test_mcp_rejects_boolean_timing_values(tracks, format_name, option):
    async with Client(server.create_server()) as client:
        result = await client.call_tool(
            "get_video_detail",
            {
                "bvid": BVID,
                "fetch_subtitles": True,
                "subtitle_format": format_name,
                option: True,
            },
            raise_on_error=False,
        )
    assert result.is_error
    assert "received a boolean" in result.content[0].text
    assert not tracks


def test_cli_returns_precise_cues_for_selected_page(tracks, capsys):
    args = {
        "bvid": f"https://www.bilibili.com/video/{BVID}?p=2",
        "fetch_subtitles": True,
        "subtitle_format": "segments",
        "subtitle_end_sec": 2,
    }
    assert cli.main(["call", "get_video_detail", "--args", json.dumps(args)]) == 0
    result = json.loads(capsys.readouterr().out)
    validate(result, VideoDetailResponse.model_json_schema())
    subtitles = result["subtitles"]
    assert subtitles["scope"]["returned_pages"] == [2]
    assert subtitles["tracks"][0]["segments"] == [
        {"start_sec": 0, "end_sec": 1, "text": "P2 start"},
    ]
    assert tracks == {"202-zh": 1}


@pytest.mark.parametrize(
    "options",
    [
        {
            "subtitle_format": "anchors",
            "subtitle_anchor_interval_sec": 30,
            "subtitle_anchor_interval_lines": 30,
        },
        {"subtitle_format": "anchors", "subtitle_anchor_interval_sec": 0},
        {"subtitle_anchor_interval_lines": 2},
        {"subtitle_start_sec": 2},
        {"subtitle_format": "anchors", "subtitle_mode": "minimal"},
        {
            "subtitle_format": "segments",
            "subtitle_scope": "all",
            "subtitle_end_sec": 250,
        },
        {"subtitle_format": "segments", "subtitle_start_sec": -1},
        {
            "subtitle_format": "segments",
            "subtitle_start_sec": 250,
            "subtitle_end_sec": 250,
        },
    ],
)
def test_cli_rejects_invalid_timing_options(tracks, capsys, options):
    args = {"bvid": BVID, "fetch_subtitles": True, **options}
    assert cli.main(["call", "get_video_detail", "--args", json.dumps(args)]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error"]["reason"] == "invalid_subtitle_selection"
    assert not tracks
