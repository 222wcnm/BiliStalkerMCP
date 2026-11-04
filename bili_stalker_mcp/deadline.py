"""Manage caller budgets and cancellation of shared cached work."""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from .errors import ToolTimeoutError

_deadline: ContextVar[float | None] = ContextVar("tool_deadline", default=None)
_P = ParamSpec("_P")
_R = TypeVar("_R")


def get_deadline() -> float | None:
    return _deadline.get()


def without_request_deadline(
    function: Callable[_P, Coroutine[Any, Any, _R]],
) -> Callable[_P, Coroutine[Any, Any, _R]]:
    """Let async-lru's active waiters own cancellation of shared work."""
    active: dict[tuple[Any, ...], set[asyncio.Task[Any]]] = {}

    @wraps(function)
    async def run(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        task = asyncio.current_task()
        key = (args, tuple(kwargs.items()))
        if task is not None:
            active.setdefault(key, set()).add(task)

            def finished(done: asyncio.Task[Any]) -> None:
                tasks = active.get(key)
                if tasks is not None:
                    tasks.discard(done)
                    if not tasks:
                        active.pop(key, None)

            # async-lru's completion callback was registered before the worker starts.
            task.add_done_callback(finished)
        token = _deadline.set(None)
        try:
            return await function(*args, **kwargs)
        finally:
            _deadline.reset(token)

    setattr(run, "_cache_work", active)
    return run


async def wait_cached(
    cache: Callable[_P, Awaitable[_R]], *args: _P.args, **kwargs: _P.kwargs
) -> _R:
    """Drain cancelled work before a same-key retry can replace its cache entry."""
    active = getattr(cache, "_cache_work", {})
    key = (args, tuple(kwargs.items()))
    loop = asyncio.get_running_loop()

    def pending_cleanup() -> list[asyncio.Task[Any]]:
        return [
            task
            for task in active.get(key, set())
            if task.get_loop() is loop and (task.cancelling() or task.done())
        ]

    if not getattr(cache, "cache_contains")(*args, **kwargs):
        # Flush callbacks for a worker cancelled before its body could register.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    while pending := pending_cleanup():
        await asyncio.shield(asyncio.gather(*pending, return_exceptions=True))
        # gather() may finish synchronously for done tasks; their callbacks must run.
        await asyncio.sleep(0)
    try:
        return await cache(*args, **kwargs)
    except asyncio.CancelledError:
        cancelled = pending_cleanup()
        if cancelled:
            await asyncio.shield(asyncio.gather(*cancelled, return_exceptions=True))
        else:
            # A worker cancelled before its first step has not registered itself.
            # Let its task and then async-lru's completion callback run in order.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        raise


@asynccontextmanager
async def deadline_scope(deadline: float | None) -> AsyncIterator[None]:
    inherited = get_deadline()
    if inherited is not None:
        deadline = inherited if deadline is None else min(deadline, inherited)
    if deadline is not None and deadline <= time.monotonic():
        raise ToolTimeoutError()
    token = _deadline.set(deadline)
    timer = asyncio.timeout_at(deadline)
    try:
        try:
            async with timer:
                yield
        except TimeoutError:
            if timer.expired():
                raise ToolTimeoutError() from None
            raise
    finally:
        _deadline.reset(token)
