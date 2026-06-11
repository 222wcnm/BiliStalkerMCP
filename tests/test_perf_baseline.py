import pytest

from scripts import perf_baseline


@pytest.mark.asyncio
async def test_dynamics_runner_uses_current_service_signature(monkeypatch):
    captured = {}

    async def fake_fetch_user_dynamics(**kwargs):
        captured.update(kwargs)
        return {"dynamics": []}

    monkeypatch.setattr(
        perf_baseline.core,
        "fetch_user_dynamics",
        fake_fetch_user_dynamics,
    )

    result = await perf_baseline._available_tools()["dynamics"](42, 3, "credential")

    assert result == {"dynamics": []}
    assert captured == {
        "user_id": 42,
        "limit": 3,
        "cred": "credential",
        "dynamic_type": "ALL",
    }
