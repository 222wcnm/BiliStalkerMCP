import asyncio
import logging
import random
import time
from typing import Awaitable, TypeVar

from ..config import REQUEST_JITTER_MAX_MS, REQUEST_JITTER_MIN_MS
from ..observability import (
    add_throttle_sleep_ms,
    add_upstream_duration_ms,
    get_request_id,
    register_upstream_call,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def timed_upstream_call(awaitable: Awaitable[T]) -> T:
    """Measure one upstream call and apply light jitter after the first call."""
    call_count = register_upstream_call()

    if (
        get_request_id() is not None
        and call_count > 1
        and REQUEST_JITTER_MAX_MS > 0
        and REQUEST_JITTER_MAX_MS >= REQUEST_JITTER_MIN_MS
    ):
        sleep_ms = random.uniform(REQUEST_JITTER_MIN_MS, REQUEST_JITTER_MAX_MS)
        logger.debug(
            "Applying upstream jitter before call %s: %.0fms", call_count, sleep_ms
        )
        add_throttle_sleep_ms(sleep_ms)
        await asyncio.sleep(sleep_ms / 1000.0)

    started = time.perf_counter()
    try:
        return await awaitable
    finally:
        add_upstream_duration_ms((time.perf_counter() - started) * 1000.0)
