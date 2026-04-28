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
        "sign": "bio",
        "following": None,
        "follower": None,
    }
    assert metrics["upstream_call_count"] == 2
    assert metrics["upstream_block_count"] == 1
    assert metrics["upstream_rate_limit_count"] == 0
