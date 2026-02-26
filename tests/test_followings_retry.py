import pytest

from bili_stalker_mcp.services.user_service import fetch_user_followings


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_fetch_user_followings_retries_retryable_codes(monkeypatch):
    sleep_calls = []
    calls = {"count": 0}

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    class FakeClient:
        async def get(self, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return _FakeResponse({"code": -509, "message": "too many requests"})
            if calls["count"] == 2:
                return _FakeResponse({"code": -412, "message": "blocked"})
            return _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "list": [{"mid": 1001, "uname": "alice", "sign": "hello"}],
                        "total": 1,
                    },
                }
            )

    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service.get_shared_http_client",
        lambda: FakeClient(),
    )

    result = await fetch_user_followings(user_id=1, page=1, limit=20, cred=None)

    assert calls["count"] == 3
    assert len(sleep_calls) == 2
    assert result["total"] == 1
    assert result["followings"] == [{"mid": 1001, "uname": "alice", "sign": "hello"}]


@pytest.mark.asyncio
async def test_fetch_user_followings_does_not_retry_private_error(monkeypatch):
    sleep_calls = []
    calls = {"count": 0}

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    class FakeClient:
        async def get(self, *args, **kwargs):
            calls["count"] += 1
            return _FakeResponse({"code": 2207, "message": "private"})

    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service.get_shared_http_client",
        lambda: FakeClient(),
    )

    with pytest.raises(ValueError, match="private"):
        await fetch_user_followings(user_id=1, page=1, limit=20, cred=None)

    assert calls["count"] == 1
    assert sleep_calls == []
