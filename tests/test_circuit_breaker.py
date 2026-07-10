import pytest

from bili_stalker_mcp.errors import RiskControlError
from bili_stalker_mcp.infra.circuit_breaker import RiskControlCircuitBreaker


def test_risk_control_circuit_opens_after_threshold():
    circuit = RiskControlCircuitBreaker(
        threshold=3,
        window_seconds=600,
        cooldown_seconds=1800,
    )

    assert circuit.record_failure(now=100.0).is_open is False
    assert circuit.record_failure(now=200.0).is_open is False

    snapshot = circuit.record_failure(now=300.0)

    assert snapshot.is_open is True
    assert snapshot.retry_after == 1800


def test_risk_control_circuit_blocks_during_cooldown(monkeypatch):
    circuit = RiskControlCircuitBreaker(
        threshold=1,
        window_seconds=600,
        cooldown_seconds=1800,
    )

    circuit.record_failure(now=100.0)
    monkeypatch.setattr(
        "bili_stalker_mcp.infra.circuit_breaker.time.monotonic", lambda: 101.0
    )

    with pytest.raises(RiskControlError):
        circuit.ensure_request_allowed()


def test_risk_control_circuit_probe_success_resets_after_cooldown():
    circuit = RiskControlCircuitBreaker(
        threshold=1,
        window_seconds=600,
        cooldown_seconds=10,
    )

    circuit.record_failure(now=100.0)
    assert circuit.snapshot(now=111.0).is_open is False

    circuit.record_success()

    assert circuit.snapshot(now=112.0).event_count == 0
    assert circuit.snapshot(now=112.0).is_open is False


def test_risk_control_circuit_probe_failure_reopens_immediately():
    circuit = RiskControlCircuitBreaker(
        threshold=3,
        window_seconds=600,
        cooldown_seconds=10,
    )

    circuit.record_failure(now=100.0)
    circuit.record_failure(now=101.0)
    circuit.record_failure(now=102.0)
    assert circuit.snapshot(now=113.0).is_open is False

    snapshot = circuit.record_failure(now=114.0)

    assert snapshot.is_open is True
    assert snapshot.retry_after == 10
