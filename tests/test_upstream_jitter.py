import asyncio

import pytest

from bili_stalker_mcp.infra import upstream
from bili_stalker_mcp.observability import (
    _metrics_state_var,
    begin_request,
    recent_risk_pressure,
    record_risk_pressure,
    reset_risk_pressure,
    snapshot_metrics,
)


@pytest.fixture(autouse=True)
def _isolated_jitter(monkeypatch):
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MIN_MS", 1)
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MAX_MS", 1)
    monkeypatch.setattr(upstream, "REQUEST_JITTER_BUDGET_MS", 10_000)
    monkeypatch.setattr(upstream, "RISK_PRESSURE_WINDOW_SECONDS", 300)
    monkeypatch.setattr(upstream, "has_configured_credential", lambda: True)
    reset_risk_pressure()
    # Drop any request context leaked from earlier tests in this process.
    _metrics_state_var.set(None)
    yield
    reset_risk_pressure()


async def _run_calls(count: int) -> None:
    begin_request("jitter-test")
    for _ in range(count):
        await upstream.timed_upstream_call(asyncio.sleep(0))


def _throttle_ms() -> float:
    return float(snapshot_metrics()["throttle_sleep_ms"])


@pytest.mark.asyncio
async def test_first_upstream_call_never_jitters():
    await _run_calls(1)
    assert _throttle_ms() == 0.0


@pytest.mark.asyncio
async def test_always_mode_jitters_subsequent_calls(monkeypatch):
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "always")
    await _run_calls(2)
    assert _throttle_ms() > 0.0


@pytest.mark.asyncio
async def test_never_mode_skips_jitter(monkeypatch):
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "never")
    await _run_calls(3)
    assert _throttle_ms() == 0.0


@pytest.mark.asyncio
async def test_adaptive_skips_jitter_with_configured_credential(monkeypatch):
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "adaptive")
    await _run_calls(3)
    assert _throttle_ms() == 0.0


@pytest.mark.asyncio
async def test_adaptive_jitters_when_anonymous(monkeypatch):
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "adaptive")
    monkeypatch.setattr(upstream, "has_configured_credential", lambda: False)
    await _run_calls(2)
    assert _throttle_ms() > 0.0


@pytest.mark.asyncio
async def test_adaptive_jitters_after_recent_risk_pressure(monkeypatch):
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "adaptive")
    record_risk_pressure()
    await _run_calls(2)
    assert _throttle_ms() > 0.0


@pytest.mark.asyncio
async def test_budget_caps_total_jitter_sleep_per_request(monkeypatch):
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "always")
    monkeypatch.setattr(upstream, "REQUEST_JITTER_BUDGET_MS", 1)
    await _run_calls(4)
    assert _throttle_ms() == 1.0


@pytest.mark.asyncio
async def test_jitter_outside_request_context_is_skipped(monkeypatch):
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "always")
    for _ in range(2):
        await upstream.timed_upstream_call(asyncio.sleep(0))
    assert _throttle_ms() == 0.0


def test_recent_risk_pressure_window_semantics():
    assert recent_risk_pressure(0) is False

    record_risk_pressure()
    assert recent_risk_pressure(300) is True

    reset_risk_pressure()
    assert recent_risk_pressure(300) is False


def test_jitter_enabled_for_call_reflects_mode(monkeypatch):
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "always")
    assert upstream.jitter_enabled_for_call() is True

    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "never")
    assert upstream.jitter_enabled_for_call() is False

    monkeypatch.setattr(upstream, "REQUEST_JITTER_MAX_MS", 0)
    monkeypatch.setattr(upstream, "REQUEST_JITTER_MODE", "always")
    assert upstream.jitter_enabled_for_call() is False
