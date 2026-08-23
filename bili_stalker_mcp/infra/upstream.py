import asyncio
import logging
import random
import time
from typing import Awaitable, TypeVar

from ..config import (
    REQUEST_JITTER_BUDGET_MS,
    REQUEST_JITTER_MAX_MS,
    REQUEST_JITTER_MIN_MS,
    REQUEST_JITTER_MODE,
    RISK_PRESSURE_WINDOW_SECONDS,
)
from ..credentials import has_configured_credential
from ..observability import (
    add_throttle_sleep_ms,
    add_upstream_duration_ms,
    get_request_id,
    get_throttle_sleep_ms,
    recent_risk_pressure,
    register_upstream_call,
)
from .circuit_breaker import record_risk_control_success

logger = logging.getLogger(__name__)

T = TypeVar("T")


def jitter_enabled_for_call() -> bool:
    """Decide whether the next upstream call should carry jitter sleep.

    "always"/"never" force the behavior; "adaptive" (default) sleeps only when
    the process looks exposed to risk control: no configured login, or a
    412/429/403 seen within RISK_PRESSURE_WINDOW_SECONDS.
    """
    if REQUEST_JITTER_MODE == "never":
        return False
    if REQUEST_JITTER_MAX_MS <= 0 or REQUEST_JITTER_MAX_MS < REQUEST_JITTER_MIN_MS:
        return False
    if REQUEST_JITTER_MODE == "always":
        return True

    if recent_risk_pressure(RISK_PRESSURE_WINDOW_SECONDS):
        return True
    return not has_configured_credential()


async def timed_upstream_call(awaitable: Awaitable[T]) -> T:
    """Measure one upstream call and apply jitter after the first call."""
    call_count = register_upstream_call()

    if get_request_id() is not None and call_count > 1 and jitter_enabled_for_call():
        budget_remaining_ms = REQUEST_JITTER_BUDGET_MS - get_throttle_sleep_ms()
        if budget_remaining_ms > 0:
            sleep_ms = min(
                random.uniform(REQUEST_JITTER_MIN_MS, REQUEST_JITTER_MAX_MS),
                budget_remaining_ms,
            )
            logger.debug(
                "Applying upstream jitter before call %s: %.0fms", call_count, sleep_ms
            )
            add_throttle_sleep_ms(sleep_ms)
            await asyncio.sleep(sleep_ms / 1000.0)

    started = time.perf_counter()
    try:
        result = await awaitable
        if not hasattr(result, "status_code"):
            record_risk_control_success()
        return result
    finally:
        add_upstream_duration_ms((time.perf_counter() - started) * 1000.0)
