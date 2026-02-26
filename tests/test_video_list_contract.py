from datetime import datetime

import pytest

from bili_stalker_mcp.services.user_service import fetch_user_videos


@pytest.mark.asyncio
async def test_fetch_user_videos_is_lightweight_and_returns_v3_keys(monkeypatch):
    calls = {"get_videos": 0, "video_detail_ctor": 0}

    class FakeUser:
        def __init__(self, uid, credential):
            self.uid = uid
            self.credential = credential

        async def get_videos(self, pn, ps):
            calls["get_videos"] += 1
            assert pn == 1
            assert ps == 3
            return {
                "list": {
                    "vlist": [
                        {
                            "aid": 1,
                            "bvid": "BV1xx411c7mD",
                            "title": "demo-1",
                            "description": "desc-1",
                            "author": "alice",
                            "length": "01:23",
                            "created": 1700000000,
                            "play": 100,
                            "review": None,
                            "comment": 7,
                            "pic": "https://example.com/1.jpg",
                            "like": 999,
                            "subtitle": {"has_subtitle": True},
                        },
                        {
                            "aid": 2,
                            "title": "demo-2",
                            "description": "desc-2",
                            "author": "bob",
                            "length": "02:34",
                            "created": 1700000300,
                            "play": "200",
                            "review": 11,
                            "comment": 999,
                        },
                        {
                            "aid": 3,
                            "title": "demo-3",
                            "description": "desc-3",
                            "author": "carol",
                            "length": "03:45",
                            "created": 1700000600,
                            "play": "300",
                            "review": 0,
                            "video_review": 12,
                            "comment": 888,
                        },
                    ]
                },
                "page": {"count": 22},
            }

    class FailVideoDetailClient:
        def __init__(self, *args, **kwargs):
            calls["video_detail_ctor"] += 1
            raise AssertionError(
                "video detail client must not be used by list endpoint"
            )

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.user.User", FakeUser)
    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service.video.Video",
        FailVideoDetailClient,
    )

    result = await fetch_user_videos(user_id=1, page=1, limit=3, cred=None)

    assert calls["get_videos"] == 1
    assert calls["video_detail_ctor"] == 0
    assert set(result.keys()) == {"videos", "total"}
    assert result["total"] == 22
    assert len(result["videos"]) == 3

    expected_keys = {
        "bvid",
        "aid",
        "title",
        "description",
        "author",
        "length",
        "created_time",
        "play",
        "review",
    }
    first = result["videos"][0]
    second = result["videos"][1]
    third = result["videos"][2]

    assert set(first.keys()) == expected_keys
    assert set(second.keys()) == expected_keys
    assert first["author"] == "alice"
    assert first["review"] == 7
    assert second["review"] == 11
    assert third["review"] == 12
    assert first["play"] == 100
    assert second["play"] == 200
    assert third["play"] == 300
    datetime.strptime(first["created_time"], "%Y-%m-%d %H:%M")
    datetime.strptime(second["created_time"], "%Y-%m-%d %H:%M")
    datetime.strptime(third["created_time"], "%Y-%m-%d %H:%M")
    assert "pic" not in first
    assert "like" not in first
    assert "subtitle" not in first
