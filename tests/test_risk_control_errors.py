import json

import pytest

from bili_stalker_mcp.errors import (
    RISK_CONTROL_MESSAGE,
    RiskControlError,
    public_error_json,
)
from bili_stalker_mcp.infra.circuit_breaker import reset_risk_control_circuit
from bili_stalker_mcp.infra.http_client import get_json


@pytest.fixture(autouse=True)
def reset_circuit():
    reset_risk_control_circuit()
    yield
    reset_risk_control_circuit()


class _FakeResponse:
    def __init__(self, *, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text

    def json(self):
        return {"code": 0}


def test_public_risk_control_error_is_json_and_sanitized():
    raw_html = "<!DOCTYPE html><html>blocked</html>"
    exc = RiskControlError(retry_after=300)

    payload = json.loads(public_error_json(exc, request_id="req-1"))

    assert payload == {
        "code": 412,
        "reason": "risk_control",
        "retry_after": 300,
        "message": RISK_CONTROL_MESSAGE,
        "request_id": "req-1",
    }
    assert raw_html not in json.dumps(payload)


@pytest.mark.parametrize("code", [412, -412])
def test_video_risk_error_preserves_context_without_raw_details(code):
    exc = RuntimeError("private-cookie-value https://private.example/?token=secret")
    exc.code = code
    exc.retry_after = 1.2
    payload = json.loads(public_error_json(exc, tool="get_user_videos"))
    assert payload["tool"] == "get_user_videos"
    assert payload["retry_after"] == 2
    assert 'dynamic_type="VIDEO"' in payload["message"]
    assert "not a complete upload list" in payload["message"]
    assert "private" not in json.dumps(payload)


def test_nonvideo_risk_error_has_no_video_fallback_advice():
    payload = json.loads(public_error_json(RiskControlError(), tool="search_users"))
    assert payload["tool"] == "search_users"
    assert payload["retry_after"] is None
    assert "pause and retry later" in payload["message"]
    assert "get_user_dynamics" not in payload["message"]


@pytest.mark.asyncio
async def test_raw_http_412_opens_circuit_and_sanitizes_error(monkeypatch):
    calls = {"count": 0}

    class FakeClient:
        async def get(self, *args, **kwargs):
            calls["count"] += 1
            return _FakeResponse(status_code=412, text="<!DOCTYPE html>blocked")

    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MIN_MS", 0)
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MAX_MS", 0)
    monkeypatch.setattr(
        "bili_stalker_mcp.infra.http_client.get_shared_http_client",
        lambda: FakeClient(),
    )
    with pytest.raises(RiskControlError) as first:
        await get_json("https://api.bilibili.com/x/test")

    first_payload = json.loads(str(first.value))
    assert first_payload["reason"] == "risk_control"
    assert "<!DOCTYPE html>" not in str(first.value)

    with pytest.raises(RiskControlError):
        await get_json("https://api.bilibili.com/x/test")
    with pytest.raises(RiskControlError):
        await get_json("https://api.bilibili.com/x/test")
    with pytest.raises(RiskControlError):
        await get_json("https://api.bilibili.com/x/test")

    assert calls["count"] == 3
