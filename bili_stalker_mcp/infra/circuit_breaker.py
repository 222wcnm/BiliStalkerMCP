"""In-process circuit breaker for Bilibili 412 risk-control responses."""

import time
from dataclasses import dataclass

from ..config import (
    BILI_412_CIRCUIT_COOLDOWN_SECONDS,
    BILI_412_CIRCUIT_THRESHOLD,
    BILI_412_CIRCUIT_WINDOW_SECONDS,
)
from ..errors import RiskControlError, normalize_retry_after


@dataclass(frozen=True)
class CircuitSnapshot:
    is_open: bool
    retry_after: int | None
    event_count: int


class RiskControlCircuitBreaker:
    def __init__(
        self,
        *,
        threshold: int = BILI_412_CIRCUIT_THRESHOLD,
        window_seconds: int = BILI_412_CIRCUIT_WINDOW_SECONDS,
        cooldown_seconds: int = BILI_412_CIRCUIT_COOLDOWN_SECONDS,
    ) -> None:
        self.threshold = max(1, threshold)
        self.window_seconds = max(1, window_seconds)
        self.cooldown_seconds = max(1, cooldown_seconds)
        self._events: list[float] = []
        self._open_until: float | None = None
        self._probe_pending = False

    def reset(self) -> None:
        self._events.clear()
        self._open_until = None
        self._probe_pending = False

    def snapshot(self, *, now: float | None = None) -> CircuitSnapshot:
        current = time.monotonic() if now is None else now
        if self._open_until is not None and current >= self._open_until:
            self._open_until = None
            self._probe_pending = True

        retry_after = None
        if self._open_until is not None:
            retry_after = normalize_retry_after(self._open_until - current)

        self._trim_events(current)
        return CircuitSnapshot(
            is_open=self._open_until is not None,
            retry_after=retry_after,
            event_count=len(self._events),
        )

    def ensure_request_allowed(self) -> None:
        snapshot = self.snapshot()
        if snapshot.is_open:
            raise RiskControlError(retry_after=snapshot.retry_after)

    def record_success(self) -> None:
        self.reset()

    def record_failure(self, *, now: float | None = None) -> CircuitSnapshot:
        current = time.monotonic() if now is None else now
        self._trim_events(current)

        if self._probe_pending:
            self._events = [current]
            self._open_until = current + self.cooldown_seconds
            self._probe_pending = False
            return self.snapshot(now=current)

        self._events.append(current)
        if len(self._events) >= self.threshold:
            self._open_until = current + self.cooldown_seconds

        return self.snapshot(now=current)

    def _trim_events(self, now: float) -> None:
        window_start = now - self.window_seconds
        self._events = [event for event in self._events if event >= window_start]


_risk_control_circuit = RiskControlCircuitBreaker()


def ensure_risk_control_request_allowed() -> None:
    _risk_control_circuit.ensure_request_allowed()


def record_risk_control_success() -> None:
    _risk_control_circuit.record_success()


def record_risk_control_failure() -> CircuitSnapshot:
    return _risk_control_circuit.record_failure()


def risk_control_snapshot() -> CircuitSnapshot:
    return _risk_control_circuit.snapshot()


def reset_risk_control_circuit() -> None:
    _risk_control_circuit.reset()
