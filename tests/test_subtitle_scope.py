import json
from unittest.mock import AsyncMock

import pytest
from jsonschema import validate

from bili_stalker_mcp import cli, server
from bili_stalker_mcp.errors import InvalidSubtitleSelectionError
from bili_stalker_mcp.models import VideoDetailResponse
from bili_stalker_mcp.services import user_service

BVID = "BV16cj96FEmw"
P2_CID = 39360465441
P2_URL = f"https://www.bilibili.com/video/{BVID}?p=2"


@pytest.fixture(autouse=True)
def isolated_subtitle_scope(monkeypatch):
    user_service._fetch_video_detail_cached.cache_clear()
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MODE", "never")
    monkeypatch.setattr(cli, "_configure_logging", lambda: None)
    monkeypatch.setattr(
        server, "_get_credential_from_context", AsyncMock(return_value=None)
    )
    yield
    user_service._fetch_video_detail_cached.cache_clear()


@pytest.fixture
def course(monkeypatch):
    pages = [
        {
            "cid": (
                39360465134 if number == 1 else P2_CID if number == 2 else 1000 + number
            ),
            "page": number,
            "part": (
                "课程预览"
                if number == 1
                else "01_场景设置与枪托粗模" if number == 2 else f"P{number}"
            ),
            "duration": 60,
        }
        for number in range(1, 66)
    ]
    info = {
        "bvid": BVID,
        "videos": 65,
        "pages": pages,
        "subtitle": {
            "list": [
                {"lan": "zh-CN", "subtitle_url": "https://example.com/p1-inline.json"}
            ]
        },
    }
    players = {}
    texts = {"https://example.com/p1-inline.json": ("P1 inline text", None)}
    for page in pages:
        languages = ("en-US", "ai-en") if page["page"] == 1 else ("zh-CN", "en-US")
        tracks = []
        for language in languages:
            url = f"https://example.com/p{page['page']}-{language}.json"
            tracks.append({"lan": language, "subtitle_url": url})
            texts[url] = (f"P{page['page']} {language} subtitle", None)
        players[page["cid"]] = {"login_mid": 123, "subtitle": {"subtitles": tracks}}
    calls = {"info": 0, "player": [], "text": []}

    class FakeVideo:
        def __init__(self, bvid, credential):
            assert bvid == BVID

        async def get_info(self):
            calls["info"] += 1
            return info

        async def get_player_info(self, cid):
            calls["player"].append(cid)
            response = players[cid]
            if isinstance(response, Exception):
                raise response
            return response

    async def fetch_text(url, cred):
        calls["text"].append(url)
        return texts[url]

    monkeypatch.setattr(user_service.video, "Video", FakeVideo)
    monkeypatch.setattr(
        "bili_stalker_mcp.services.subtitle_service._fetch_subtitle_text", fetch_text
    )
    return {"calls": calls, "info": info, "players": players, "texts": texts}


@pytest.mark.parametrize(
    "selection",
    [
        {"bvid": P2_URL},
        {"bvid": BVID, "subtitle_page": 2},
        {"bvid": BVID, "subtitle_cid": P2_CID},
        {"bvid": P2_URL, "subtitle_page": 2},
        {"bvid": P2_URL, "subtitle_cid": P2_CID},
    ],
)
def test_cli_selects_only_p2_in_65_page_course(course, capsys, selection):
    args = {"fetch_subtitles": True, **selection}
    assert cli.main(["call", "get_video_detail", "--args", json.dumps(args)]) == 0
    result = json.loads(capsys.readouterr().out)
    subtitles = result["subtitles"]
    assert course["calls"] == {
        "info": 1,
        "player": [P2_CID],
        "text": ["https://example.com/p2-zh-CN.json"],
    }
    assert len(result["video"]["pages"]) == 65
    assert subtitles["full_text"] == "P2 zh-CN subtitle"
    assert subtitles["tracks"][0]["cid"] == P2_CID
    assert subtitles["tracks"][0]["part"] == "01_场景设置与枪托粗模"
    assert subtitles["scope"]["target_page"] == 2
    assert subtitles["scope"]["returned_pages"] == [2]
    assert subtitles["scope"]["total_pages"] == 65
    assert "64 of 65" in subtitles["scope"]["summary"]
    validate(result, VideoDetailResponse.model_json_schema())


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,track_count", [("smart", 1), ("full", 2)])
async def test_both_modes_default_to_p1_and_ignore_multi_page_inline(
    course, mode, track_count
):
    result = await user_service.fetch_video_detail(BVID, True, subtitle_mode=mode)
    subtitles = result["subtitles"]
    assert course["calls"]["player"] == [39360465134]
    assert len(course["calls"]["text"]) == track_count
    assert subtitles["track_count"] == track_count
    assert subtitles["scope"]["target_page"] == 1
    assert subtitles["scope"]["returned_pages"] == [1]
    assert "P1 en-US subtitle" in subtitles["full_text"]
    assert "inline" not in subtitles["full_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["smart", "full"])
async def test_all_scope_retains_complete_metadata_scan(course, mode):
    result = await user_service.fetch_video_detail(
        BVID, True, subtitle_mode=mode, subtitle_scope="all"
    )
    subtitles = result["subtitles"]
    assert course["calls"]["player"] == [
        page["cid"] for page in course["info"]["pages"]
    ]
    assert len(course["calls"]["text"]) == (1 if mode == "smart" else 130)
    assert subtitles["scope"]["mode"] == "all"
    assert subtitles["scope"]["target_page"] is None
    assert subtitles["scope"]["returned_pages"] == (
        [2] if mode == "smart" else list(range(1, 66))
    )
    assert all(track["text"] == "" for track in subtitles["tracks"])
    assert not subtitles["truncated"]


@pytest.mark.parametrize(
    "selection,info_calls",
    [
        ({"bvid": P2_URL, "subtitle_page": 3}, 0),
        ({"bvid": P2_URL, "subtitle_cid": 39360465134}, 1),
        ({"subtitle_page": 2, "subtitle_cid": P2_CID}, 0),
        ({"bvid": P2_URL, "subtitle_scope": "all"}, 0),
        ({"subtitle_scope": "all", "subtitle_page": 2}, 0),
        ({"subtitle_scope": "all", "subtitle_cid": P2_CID}, 0),
        ({"subtitle_page": 66}, 1),
        ({"subtitle_cid": 999}, 1),
        (
            {
                "bvid": f"https://www.bilibili.com/video/{BVID}?p=oops&vd_source=private-token"
            },
            0,
        ),
    ],
)
def test_cli_selection_errors_are_explicit_and_stop_before_subtitle_queries(
    course, capsys, selection, info_calls
):
    args = {"bvid": BVID, "fetch_subtitles": True, **selection}
    assert cli.main(["call", "get_video_detail", "--args", json.dumps(args)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["reason"] == "invalid_subtitle_selection"
    assert error["message"]
    assert error["request_id"]
    assert "private-token" not in captured.err
    assert "https://" not in captured.err
    assert course["calls"] == {"info": info_calls, "player": [], "text": []}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection",
    [
        {"subtitle_page": 0},
        {"subtitle_cid": -1},
        {"subtitle_page": True},
        {"subtitle_scope": "invalid"},
    ],
)
async def test_service_rejects_invalid_selection_without_loading_video(
    course, selection
):
    with pytest.raises(InvalidSubtitleSelectionError):
        await user_service.fetch_video_detail(BVID, True, **selection)
    assert course["calls"]["info"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["no_tracks", "login", "metadata", "download", "budget"]
)
async def test_missing_p2_text_never_falls_back_to_other_pages(course, failure):
    mode = "smart"
    budget = 12000
    if failure == "no_tracks":
        course["players"][P2_CID]["subtitle"]["subtitles"] = []
    elif failure == "login":
        course["players"][P2_CID] = {
            "login_mid": 0,
            "need_login_subtitle": True,
            "subtitle": {"subtitles": []},
        }
    elif failure == "metadata":
        course["players"][P2_CID] = RuntimeError("metadata unavailable")
    elif failure == "download":
        course["texts"]["https://example.com/p2-zh-CN.json"] = ("", "download failed")
    else:
        mode = "full"
        budget = 1
    result = await user_service.fetch_video_detail(
        BVID, True, subtitle_page=2, subtitle_mode=mode, subtitle_max_chars=budget
    )
    subtitles = result["subtitles"]
    assert course["calls"]["player"] == [P2_CID]
    assert subtitles["full_text"] == ""
    assert subtitles["scope"]["target_page"] == 2
    assert subtitles["scope"]["returned_pages"] == []
    assert "65 of 65" in subtitles["scope"]["summary"]
    if failure in {"login", "metadata", "download"}:
        assert subtitles["errors"]
    if failure == "budget":
        assert subtitles["truncated"]


@pytest.mark.asyncio
async def test_scope_reports_partial_smart_text_and_full_budget_omissions(course):
    partial = await user_service.fetch_video_detail(
        BVID, True, subtitle_page=2, subtitle_max_chars=1
    )
    assert partial["subtitles"]["full_text"] == "P"
    assert partial["subtitles"]["truncated"]
    assert partial["subtitles"]["scope"]["returned_pages"] == [2]
    first = await user_service.fetch_video_detail(BVID, True, subtitle_mode="full")
    limited = await user_service.fetch_video_detail(
        BVID,
        True,
        subtitle_mode="full",
        subtitle_scope="all",
        subtitle_max_chars=len(first["subtitles"]["full_text"]),
    )
    assert limited["subtitles"]["full_text"] == first["subtitles"]["full_text"]
    assert limited["subtitles"]["truncated"]
    assert limited["subtitles"]["scope"]["returned_pages"] == [1]


@pytest.mark.asyncio
async def test_cache_separates_default_page_cid_url_and_all_and_returns_fresh_scope(
    course,
):
    selections = [
        {},
        {"subtitle_page": 2},
        {"subtitle_cid": P2_CID},
        {"subtitle_url_page": 2},
        {"subtitle_scope": "all"},
    ]
    for selection in selections:
        first = await user_service.fetch_video_detail(BVID, True, **selection)
        expected_page = 1 if not selection else 2
        assert first["subtitles"]["scope"]["returned_pages"] == [expected_page]
        first["subtitles"]["scope"]["returned_pages"].append(999)
        first["subtitles"]["scope"]["summary"] = "mutated"
        second = await user_service.fetch_video_detail(BVID, True, **selection)
        assert second["subtitles"]["scope"]["returned_pages"] == [expected_page]
        assert second["subtitles"]["scope"]["summary"] != "mutated"
    assert course["calls"]["info"] == 5


@pytest.mark.asyncio
async def test_minimal_resolves_p2_without_subtitle_queries(course):
    result = await user_service.fetch_video_detail(
        BVID, True, subtitle_mode="minimal", subtitle_url_page=2
    )
    scope = result["subtitles"]["scope"]
    assert scope["target_page"] == 2
    assert scope["returned_pages"] == []
    assert "skipped" in scope["summary"]
    assert course["calls"] == {"info": 1, "player": [], "text": []}


def test_disabled_subtitles_ignore_url_page_and_do_not_use_sdk(
    course, monkeypatch, capsys
):
    raw_get = AsyncMock(return_value={"code": 0, "data": course["info"]})
    monkeypatch.setattr(user_service, "get_json", raw_get)
    args = {"bvid": P2_URL, "subtitle_scope": "all", "subtitle_page": 3}
    assert cli.main(["call", "get_video_detail", "--args", json.dumps(args)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["subtitles"]["scope"] is None
    assert raw_get.await_count == 1
    assert course["calls"] == {"info": 0, "player": [], "text": []}
