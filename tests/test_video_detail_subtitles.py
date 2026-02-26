import pytest

from bili_stalker_mcp.services.user_service import fetch_video_detail


@pytest.mark.asyncio
async def test_fetch_video_detail_fetches_single_track_in_smart_mode(monkeypatch):
    calls = {
        "get_info": 0,
        "get_pages": 0,
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
            }

        async def get_pages(self):
            calls["get_pages"] += 1
            return [
                {"cid": 101, "page": 1, "part": "P1", "duration": 30},
                {"cid": 202, "page": 2, "part": "P2", "duration": 45},
            ]

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
        "bili_stalker_mcp.services.user_service._fetch_subtitle_text",
        fake_fetch_subtitle_text,
    )

    result = await fetch_video_detail(
        bvid="BV1xx411c7mD",
        fetch_subtitles=True,
        cred=None,
    )

    assert calls["get_info"] == 1
    assert calls["get_pages"] == 1
    assert calls["get_subtitle"] == 2
    assert calls["subtitle_text"] == ["https://example.com/zh.json"]

    assert set(result.keys()) == {"video", "subtitles"}
    assert result["video"]["tags"] == ["tag-a", "tag-b"]

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
            return {"bvid": "BV1xx411c7mD", "aid": 123, "stat": {}}

        async def get_pages(self):
            return [{"cid": 101, "page": 1, "part": "P1", "duration": 30}]

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
        "bili_stalker_mcp.services.user_service._fetch_subtitle_text",
        fake_fetch_subtitle_text,
    )

    result = await fetch_video_detail(
        bvid="BV1xx411c7mD",
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
    calls = {"get_subtitle": 0}

    class FakeVideo:
        def __init__(self, bvid, credential):
            self.bvid = bvid
            self.credential = credential

        async def get_info(self):
            return {"bvid": "BV1xx411c7mD", "aid": 123, "stat": {}}

        async def get_pages(self):
            return [{"cid": 101, "page": 1, "part": "P1", "duration": 30}]

        async def get_subtitle(self, cid):
            calls["get_subtitle"] += 1
            return {"subtitles": []}

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.video.Video", FakeVideo)

    result = await fetch_video_detail(
        bvid="BV1xx411c7mD",
        cred=None,
    )

    assert calls["get_subtitle"] == 0
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
