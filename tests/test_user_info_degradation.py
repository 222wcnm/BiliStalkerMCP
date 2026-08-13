import pytest

from bili_stalker_mcp.observability import begin_request, snapshot_metrics
from bili_stalker_mcp.services.user_service import (
    _fetch_user_info_cached,
    fetch_user_info,
)


@pytest.fixture(autouse=True)
def clear_user_info_cache():
    _fetch_user_info_cached.cache_clear()
    yield
    _fetch_user_info_cached.cache_clear()


class _FakeResponse:
    def __init__(self, *, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = ""

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_fetch_user_info_degrades_relation_stat_when_blocked(monkeypatch):
    class FakeUser:
        def __init__(self, uid, credential):
            self.uid = uid
            self.credential = credential

        async def get_user_info(self):
            return {
                "mid": 42,
                "name": "demo",
                "sign": "bio",
            }

    class FakeClient:
        async def get(self, *args, **kwargs):
            return _FakeResponse(status_code=412)

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.user.User", FakeUser)
    monkeypatch.setattr(
        "bili_stalker_mcp.infra.http_client.get_shared_http_client",
        lambda: FakeClient(),
    )
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MIN_MS", 0)
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MAX_MS", 0)
    begin_request("user-info-blocked")

    result = await fetch_user_info(user_id=42, cred=None)
    metrics = snapshot_metrics()

    assert result == {
        "mid": 42,
        "name": "demo",
        "face": None,
        "sign": "bio",
        "level": None,
        "sex": None,
        "birthday": None,
        "school": None,
        "profession": None,
        "official": None,
        "vip": None,
        "is_banned": None,
        "is_senior_member": None,
        "live_room": None,
        "following": None,
        "follower": None,
        "total_video_views": None,
        "total_article_views": None,
        "total_likes": None,
    }
    assert metrics["upstream_call_count"] == 2
    assert metrics["upstream_block_count"] == 1
    assert metrics["upstream_rate_limit_count"] == 0


@pytest.mark.asyncio
async def test_fetch_user_info_returns_rich_profile_and_up_stat(monkeypatch):
    class FakeCredential:
        bili_jct = "csrf-token"

        def get_cookies(self):
            return {}

    class FakeUser:
        def __init__(self, uid, credential):
            self.uid = uid
            self.credential = credential

        async def get_user_info(self):
            return {
                "mid": 946974,
                "name": "影视飓风",
                "face": "https://i0.hdslb.com/bfs/face/avatar.jpg",
                "sign": "商务合作请联系……",
                "level": 6,
                "sex": "保密",
                "birthday": "05-16",
                "silence": 0,
                "is_senior_member": 1,
                "school": {"name": ""},
                "profession": {"name": "摄影师", "title": ""},
                "official": {"role": 7, "title": "2025百大UP主", "desc": ""},
                "vip": {"status": 1, "label": {"text": "十年大会员"}},
                "live_room": {
                    "roomStatus": 1,
                    "liveStatus": 1,
                    "url": "https://live.bilibili.com/123",
                    "title": "修片直播",
                    "roomid": 123,
                    "watched_show": {"num": 4567},
                },
            }

        async def get_up_stat(self):
            return {
                "archive": {"view": 987654321},
                "article": {"view": 12345},
                "likes": 55555,
            }

    class FakeRelationResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "code": 0,
                "data": {"following": 30, "follower": 14000000},
            }

    class FakeClient:
        async def get(self, *args, **kwargs):
            return FakeRelationResponse()

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.user.User", FakeUser)
    monkeypatch.setattr(
        "bili_stalker_mcp.infra.http_client.get_shared_http_client",
        lambda: FakeClient(),
    )
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MIN_MS", 0)
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MAX_MS", 0)
    begin_request("user-info-rich")

    result = await fetch_user_info(user_id=946974, cred=FakeCredential())

    assert result == {
        "mid": 946974,
        "name": "影视飓风",
        "face": "https://i0.hdslb.com/bfs/face/avatar.jpg",
        "sign": "商务合作请联系……",
        "level": 6,
        "sex": None,
        "birthday": "05-16",
        "school": None,
        "profession": "摄影师",
        "official": {"role": 7, "title": "2025百大UP主"},
        "vip": {"status": True, "label": "十年大会员"},
        "is_banned": False,
        "is_senior_member": True,
        "live_room": {
            "is_live": True,
            "title": "修片直播",
            "url": "https://live.bilibili.com/123",
            "watched": 4567,
        },
        "following": 30,
        "follower": 14000000,
        "total_video_views": 987654321,
        "total_article_views": 12345,
        "total_likes": 55555,
    }
