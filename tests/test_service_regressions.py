import httpx
import pytest

from bili_stalker_mcp.errors import RiskControlError
from bili_stalker_mcp.infra import upstream
from bili_stalker_mcp.infra.circuit_breaker import reset_risk_control_circuit
from bili_stalker_mcp.retry import RetryableBiliApiError
from bili_stalker_mcp.services import dynamic_service, user_service


@pytest.fixture(autouse=True)
def isolated_services(monkeypatch):
    user_service._fetch_video_detail_cached.cache_clear()
    dynamic_service._fetch_user_dynamics_cached.cache_clear()
    reset_risk_control_circuit()
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "never")
    monkeypatch.setattr(dynamic_service, "LAZY_ENABLED", False)
    yield
    user_service._fetch_video_detail_cached.cache_clear()
    dynamic_service._fetch_user_dynamics_cached.cache_clear()
    reset_risk_control_circuit()


@pytest.mark.asyncio
async def test_video_detail_cache_isolates_nested_response_mutations(monkeypatch):
    calls = 0

    async def fake_get_json(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {
            "code": 0,
            "data": {
                "title": "original",
                "stat": {"view": 12},
                "pages": [{"cid": 1, "part": "original part"}],
            },
        }

    monkeypatch.setattr(user_service, "get_json", fake_get_json)
    first = await user_service.fetch_video_detail("BV1xx411c7mD")
    first["video"]["title"] = "changed"
    first["video"]["stat"]["view"] = -1
    first["video"]["pages"][0]["part"] = "changed"
    first["subtitles"]["errors"].append("injected")

    second = await user_service.fetch_video_detail("BV1xx411c7mD")
    assert second["video"]["title"] == "original"
    assert second["video"]["stat"]["view"] == 12
    assert second["video"]["pages"][0]["part"] == "original part"
    assert second["subtitles"]["errors"] == []
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["transient", "exhausted", "risk"])
async def test_dynamic_retry_preserves_completed_pages(monkeypatch, failure):
    calls = []

    class FakeUser:
        def __init__(self, uid, credential):
            pass

        async def get_dynamics_new(self, offset):
            calls.append(offset)
            page = int(offset or 0)
            if page == 4:
                if failure == "risk":
                    raise RetryableBiliApiError(-412, "blocked")
                if failure == "exhausted" or calls.count("4") == 1:
                    raise httpx.ConnectError("temporary connection failure")
            return {
                "items": [
                    {
                        "id_str": str(page),
                        "type": "DYNAMIC_TYPE_WORD",
                        "modules": {
                            "module_dynamic": {"desc": {"text": str(page)}},
                        },
                    }
                ],
                "has_more": page < 4,
                "offset": str(page + 1) if page < 4 else "",
            }

    async def no_sleep(delay):
        pass

    monkeypatch.setattr(dynamic_service.user, "User", FakeUser)
    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", no_sleep)
    if failure == "transient":
        result = await dynamic_service.fetch_user_dynamics(1, 5, object(), "TEXT")
        assert [item["dynamic_id"] for item in result["dynamics"]] == [
            "0",
            "1",
            "2",
            "3",
            "4",
        ]
        assert result["has_more"] is False
        assert calls == ["", "1", "2", "3", "4", "4"]
    else:
        expected_error = RiskControlError if failure == "risk" else httpx.ConnectError
        with pytest.raises(expected_error):
            await dynamic_service.fetch_user_dynamics(1, 5, object(), "TEXT")
        attempts = 1 if failure == "risk" else 4
        assert calls == ["", "1", "2", "3"] + ["4"] * attempts
        assert dynamic_service._fetch_user_dynamics_cached.cache_info().currsize == 0
