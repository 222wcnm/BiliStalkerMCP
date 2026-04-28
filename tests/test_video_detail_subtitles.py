import pytest

from bili_stalker_mcp.observability import begin_request, snapshot_metrics
from bili_stalker_mcp.retry import RetryableBiliApiError
from bili_stalker_mcp.services.user_service import (
    _fetch_video_detail_cached,
    fetch_video_detail,
)


@pytest.fixture(autouse=True)
def clear_video_detail_cache():
    _fetch_video_detail_cached.cache_clear()
    yield
    _fetch_video_detail_cached.cache_clear()


@pytest.mark.asyncio
async def test_fetch_video_detail_falls_back_to_subtitle_api_for_multi_page_smart_mode(
    monkeypatch,
):
    calls = {
        "get_info": 0,
        "get_subtitle": 0,
        "subtitle_text": [],
    }

    class FakeVideo:
        def __init__(self, bvid, credential):
            self.bvid = bvid
            self.credential = credential

        async def get_info(self):
            calls["get_info"] += 1
            return {
                "bvid": "BV1xx411c7mD",
                "aid": 123,
                "title": "demo video",
                "desc": "demo desc",
                "pubdate": 1700000000,
                "stat": {
                    "view": 100,
                    "danmaku": 2,
                    "reply": 3,
                    "favorite": 4,
                    "coin": 5,
                    "share": 6,
                    "like": 7,
                },
                "tag": [{"tag_name": "tag-a"}, {"name": "tag-b"}],
                "pages": [
                    {"cid": 101, "page": 1, "part": "P1", "duration": 30},
                    {"cid": 202, "page": 2, "part": "P2", "duration": 45},
                ],
            }

        async def get_subtitle(self, cid):
            calls["get_subtitle"] += 1
            if cid == 101:
                return {
                    "subtitles": [
                        {
                            "lan": "zh-CN",
                            "lan_doc": "Chinese",
                            "subtitle_url": "https://example.com/zh.json",
                        },
                        {
                            "lan": "ai-en",
                            "lan_doc": "English",
                            "subtitle_url": "https://example.com/en.json",
                            "ai_type": 1,
                        },
                    ]
                }
            raise RuntimeError("metadata unavailable")

    async def fake_fetch_subtitle_text(subtitle_url, cred):
        calls["subtitle_text"].append(subtitle_url)
        if subtitle_url.endswith("zh.json"):
            return "zh line 1\nzh line 2", None
        if subtitle_url.endswith("en.json"):
            return "en line 1\nen line 2", None
        return "", "unknown subtitle url"

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.video.Video", FakeVideo)
    monkeypatch.setattr(
        "bili_stalker_mcp.services.subtitle_service._fetch_subtitle_text",
        fake_fetch_subtitle_text,
    )

    result = await fetch_video_detail(
        bvid="BV1xx411c7mD",
        fetch_subtitles=True,
        cred=None,
    )

    assert calls["get_info"] == 1
    assert calls["get_subtitle"] == 2
    assert calls["subtitle_text"] == ["https://example.com/zh.json"]

    assert set(result.keys()) == {"video", "subtitles"}
    assert result["video"]["tags"] == ["tag-a", "tag-b"]
    assert result["video"]["pages"] == [
        {"cid": 101, "page": 1, "part": "P1", "duration": 30},
        {"cid": 202, "page": 2, "part": "P2", "duration": 45},
    ]

    subtitles = result["subtitles"]
    assert subtitles["enabled"] is True
    assert subtitles["mode"] == "smart"
    assert subtitles["requested_language"] == "auto"
    assert subtitles["available_languages"] == ["zh-CN", "ai-en"]
    assert subtitles["selected_language"] == "zh-CN"
    assert subtitles["fallback_reason"] is None
    assert subtitles["track_count"] == 1
    assert subtitles["dropped_tracks"] == 1
    assert len(subtitles["tracks"]) == 1
    assert subtitles["tracks"][0]["cid"] == 101
    assert subtitles["tracks"][0]["part"] == "P1"
    assert subtitles["tracks"][0]["is_ai_generated"] is False
    assert subtitles["full_text"] == "zh line 1\nzh line 2"
    assert subtitles["returned_chars"] == len("zh line 1\nzh line 2")
    assert subtitles["truncated"] is False
    assert any(
        "cid 202: subtitle metadata failed" in err for err in subtitles["errors"]
    )


@pytest.mark.asyncio
async def test_fetch_video_detail_smart_mode_short_circuits_single_page_inline_subtitles(
    monkeypatch,
):
    calls = {
        "get_info": 0,
        "get_subtitle": 0,
        "subtitle_text": [],
    }

    class FakeVideo:
        def __init__(self, bvid, credential):
            self.bvid = bvid
            self.credential = credential

        async def get_info(self):
            calls["get_info"] += 1
            return {
                "bvid": "BV1inline111",
                "aid": 321,
                "stat": {},
                "pages": [{"cid": 101, "page": 1, "part": "P1", "duration": 30}],
                "subtitle": {
                    "list": [
                        {
                            "lan": "zh-CN",
                            "lan_doc": "Chinese",
                            "subtitle_url": "//example.com/zh-inline.json",
                        },
                        {
                            "lan": "en-US",
                            "lan_doc": "English",
                            "subtitle_url": "https://example.com/en-inline.json",
                        },
                    ]
                },
            }

        async def get_subtitle(self, cid):
            calls["get_subtitle"] += 1
            return {"subtitles": []}

    async def fake_fetch_subtitle_text(subtitle_url, cred):
        calls["subtitle_text"].append(subtitle_url)
        if subtitle_url.endswith("zh-inline.json"):
            return "inline zh body", None
        if subtitle_url.endswith("en-inline.json"):
            return "inline en body", None
        return "", "unknown subtitle url"

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.video.Video", FakeVideo)
    monkeypatch.setattr(
        "bili_stalker_mcp.services.subtitle_service._fetch_subtitle_text",
        fake_fetch_subtitle_text,
    )

    result = await fetch_video_detail(
        bvid="BV1inline111",
        fetch_subtitles=True,
        cred=None,
    )

    subtitles = result["subtitles"]
    assert calls["get_info"] == 1
    assert calls["get_subtitle"] == 0
    assert calls["subtitle_text"] == ["https://example.com/zh-inline.json"]
    assert subtitles["mode"] == "smart"
    assert subtitles["available_languages"] == ["zh-CN", "en-US"]
    assert subtitles["selected_language"] == "zh-CN"
    assert subtitles["track_count"] == 1
    assert subtitles["dropped_tracks"] == 1
    assert subtitles["full_text"] == "inline zh body"
    assert subtitles["errors"] == []


@pytest.mark.asyncio
async def test_fetch_video_detail_invalid_inline_subtitles_fall_back_to_subtitle_api(
    monkeypatch,
):
    calls = {
        "get_subtitle": 0,
        "subtitle_text": [],
    }

    class FakeVideo:
        def __init__(self, bvid, credential):
            self.bvid = bvid
            self.credential = credential

        async def get_info(self):
            return {
                "bvid": "BV1fallback11",
                "aid": 456,
                "stat": {},
                "pages": [{"cid": 101, "page": 1, "part": "P1", "duration": 30}],
                "subtitle": {
                    "list": [
                        {
                            "lan": "zh-CN",
                            "lan_doc": "Chinese",
                        }
                    ]
                },
            }

        async def get_subtitle(self, cid):
            calls["get_subtitle"] += 1
            return {
                "subtitles": [
                    {
                        "lan": "zh-CN",
                        "lan_doc": "Chinese",
                        "subtitle_url": "https://example.com/fallback.json",
                    }
                ]
            }

    async def fake_fetch_subtitle_text(subtitle_url, cred):
        calls["subtitle_text"].append(subtitle_url)
        if subtitle_url.endswith("fallback.json"):
            return "fallback body", None
        return "", "unknown subtitle url"

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.video.Video", FakeVideo)
    monkeypatch.setattr(
        "bili_stalker_mcp.services.subtitle_service._fetch_subtitle_text",
        fake_fetch_subtitle_text,
    )

    result = await fetch_video_detail(
        bvid="BV1fallback11",
        fetch_subtitles=True,
        cred=None,
    )

    subtitles = result["subtitles"]
    assert calls["get_subtitle"] == 1
    assert calls["subtitle_text"] == ["https://example.com/fallback.json"]
    assert subtitles["track_count"] == 1
    assert subtitles["full_text"] == "fallback body"


@pytest.mark.asyncio
async def test_fetch_video_detail_marks_blocked_subtitle_downloads_in_errors(monkeypatch):
    class FakeVideo:
        def __init__(self, bvid, credential):
            self.bvid = bvid
            self.credential = credential

        async def get_info(self):
            return {
                "bvid": "BV1blocked111",
                "aid": 999,
                "stat": {},
                "pages": [{"cid": 101, "page": 1, "part": "P1", "duration": 30}],
                "subtitle": {
                    "list": [
                        {
                            "lan": "zh-CN",
                            "lan_doc": "Chinese",
                            "subtitle_url": "https://example.com/blocked.json",
                        }
                    ]
                },
            }

        async def get_subtitle(self, cid):
            return {"subtitles": []}

    async def fake_get_json(*args, **kwargs):
        raise RetryableBiliApiError(429, "HTTP rate limit from upstream")

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.video.Video", FakeVideo)
    monkeypatch.setattr(
        "bili_stalker_mcp.services.subtitle_service.get_json",
        fake_get_json,
    )

    result = await fetch_video_detail(
        bvid="BV1blocked111",
        fetch_subtitles=True,
        cred=None,
    )

    subtitles = result["subtitles"]
    assert subtitles["track_count"] == 1
    assert subtitles["full_text"] == ""
    assert any("blocked or rate-limited" in err for err in subtitles["errors"])


@pytest.mark.asyncio
async def test_fetch_video_detail_full_mode_keeps_all_tracks(monkeypatch):
    calls = {
        "get_subtitle": 0,
        "subtitle_text": [],
    }

    class FakeVideo:
        def __init__(self, bvid, credential):
            self.bvid = bvid
            self.credential = credential

        async def get_info(self):
            return {
                "bvid": "BV1full11111",
                "aid": 123,
                "stat": {},
                "pages": [{"cid": 101, "page": 1, "part": "P1", "duration": 30}],
                "subtitle": {
                    "list": [
                        {
                            "lan": "zh-CN",
                            "lan_doc": "Chinese",
                            "subtitle_url": "https://example.com/inline-zh.json",
                        }
                    ]
                },
            }

        async def get_subtitle(self, cid):
            calls["get_subtitle"] += 1
            return {
                "subtitles": [
                    {
                        "lan": "zh-CN",
                        "lan_doc": "Chinese",
                        "subtitle_url": "https://example.com/zh.json",
                    },
                    {
                        "lan": "en-US",
                        "lan_doc": "English",
                        "subtitle_url": "https://example.com/en.json",
                    },
                ]
            }

    async def fake_fetch_subtitle_text(subtitle_url, cred):
        calls["subtitle_text"].append(subtitle_url)
        if subtitle_url.endswith("zh.json"):
            return "zh body", None
        if subtitle_url.endswith("en.json"):
            return "en body", None
        return "", "unknown subtitle url"

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.video.Video", FakeVideo)
    monkeypatch.setattr(
        "bili_stalker_mcp.services.subtitle_service._fetch_subtitle_text",
        fake_fetch_subtitle_text,
    )

    result = await fetch_video_detail(
        bvid="BV1full11111",
        fetch_subtitles=True,
        subtitle_mode="full",
        cred=None,
    )

    subtitles = result["subtitles"]
    assert calls["get_subtitle"] == 1
    assert sorted(calls["subtitle_text"]) == [
        "https://example.com/en.json",
        "https://example.com/zh.json",
    ]
    assert subtitles["mode"] == "full"
    assert subtitles["track_count"] == 2
    assert len(subtitles["tracks"]) == 2
    assert subtitles["full_text"] == "zh body\nen body"
    assert subtitles["dropped_tracks"] == 0


@pytest.mark.asyncio
async def test_fetch_video_detail_defaults_to_disabled_subtitles(monkeypatch):
    calls = {"get_info": 0}

    class FakeVideo:
        def __init__(self, bvid, credential):
            self.bvid = bvid
            self.credential = credential

        async def get_info(self):
            calls["get_info"] += 1
            return {
                "bvid": "BV1disabled11",
                "aid": 123,
                "stat": {},
                "pages": [{"cid": 101, "page": 1, "part": "P1", "duration": 30}],
            }

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.video.Video", FakeVideo)

    result = await fetch_video_detail(
        bvid="BV1disabled11",
        cred=None,
    )

    assert calls["get_info"] == 1
    assert result["subtitles"] == {
        "enabled": False,
        "mode": "disabled",
        "requested_language": "auto",
        "available_languages": [],
        "selected_language": None,
        "fallback_reason": None,
        "truncated": False,
        "returned_chars": 0,
        "dropped_tracks": 0,
        "track_count": 0,
        "tracks": [],
        "full_text": "",
        "errors": [],
    }


@pytest.mark.asyncio
async def test_fetch_video_detail_records_cache_hit_metrics(monkeypatch):
    calls = {"get_info": 0}

    class FakeVideo:
        def __init__(self, bvid, credential):
            self.bvid = bvid
            self.credential = credential

        async def get_info(self):
            calls["get_info"] += 1
            return {
                "bvid": "BV1cache1111",
                "aid": 789,
                "title": "cache demo",
                "stat": {},
                "pages": [{"cid": 101, "page": 1, "part": "P1", "duration": 30}],
            }

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.video.Video", FakeVideo)

    begin_request("video-detail-cache")
    first = await fetch_video_detail(bvid="BV1cache1111", cred=None)
    second = await fetch_video_detail(bvid="BV1cache1111", cred=None)

    metrics = snapshot_metrics()

    assert first == second
    assert calls["get_info"] == 1
    assert metrics["cache"]["video_detail"] == {
        "hit": 1,
        "miss": 1,
        "total": 2,
        "hit_rate": 0.5,
    }
