import json

import pytest

from bili_stalker_mcp.errors import RiskControlError, public_error_json
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
        "message": (
            "Bilibili risk control is active; upstream requests are temporarily paused."
        ),
        "request_id": "req-1",
    }
    assert raw_html not in json.dumps(payload)


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
