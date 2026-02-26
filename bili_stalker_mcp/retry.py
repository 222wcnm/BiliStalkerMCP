"""Unified retry strategy for transient Bilibili/API network failures."""

import asyncio
import functools
import logging
import random
from typing import Any, Callable, Optional, Set, Type, TypeVar

import httpx
from bilibili_api.exceptions import ApiException

from .observability import add_retry

logger = logging.getLogger(__name__)

DEFAULT_RETRYABLE_CODES: Set[int] = {-412, -509}

T = TypeVar("T")


class RetryableBiliApiError(Exception):
    """Structured error carrying a Bilibili code for retry classification."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{message} (code={code})")


def _extract_api_error_code(exc: Exception) -> int | None:
    """Best-effort extraction of Bilibili API error code from ApiException."""
    if isinstance(exc, RetryableBiliApiError):
        return exc.code

    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code

    if exc.args:
        first = exc.args[0]
        if isinstance(first, dict):
            arg_code = first.get("code")
            if isinstance(arg_code, int):
                return arg_code

    return None


def with_retry(
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    retryable_codes: Optional[Set[int]] = None,
    retryable_exceptions: Optional[tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    default_on_exhaust: Optional[Any] = None,
    return_default: bool = False,
) -> Callable:
    """Retry async call with exponential backoff on deterministic transient failures."""
    codes = retryable_codes or DEFAULT_RETRYABLE_CODES
    exceptions = retryable_exceptions or (httpx.RequestError,)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    # First attempt is immediate. Backoff applies only to retries.
                    if attempt > 0:
                        delay = min(
                            base_delay * (2 ** (attempt - 1)) + random.uniform(0.0, 0.5),
                            max_delay,
                        )
                        logger.warning(
                            "Retry %s/%s for %s in %.2fs",
                            attempt,
                            max_retries,
                            func.__name__,
                            delay,
                        )
                        await asyncio.sleep(delay)

                    return await func(*args, **kwargs)

                except (ApiException, RetryableBiliApiError) as exc:
                    last_exception = exc
                    code = _extract_api_error_code(exc)
                    if code in codes and attempt < max_retries:
                        add_retry()
                        if on_retry:
                            on_retry(attempt + 1, exc)
                        logger.warning(
                            "Retryable API error in %s (code=%s)",
                            func.__name__,
                            code,
                        )
                        continue
                    if code in codes:
                        logger.error(
                            "Retryable API error exhausted in %s (code=%s)",
                            func.__name__,
                            code,
                        )
                    else:
                        logger.error(
                            "Non-retryable API error in %s (code=%s): %s",
                            func.__name__,
                            code,
                            exc,
                        )
                    break

                except exceptions as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        add_retry()
                        if on_retry:
                            on_retry(attempt + 1, exc)
                        logger.warning(
                            "Retryable transport error in %s: %s",
                            func.__name__,
                            type(exc).__name__,
                        )
                        continue
                    logger.error(
                        "Transport retries exhausted in %s: %s",
                        func.__name__,
                        exc,
                    )
                    break

            if return_default:
                logger.warning(
                    "All retries exhausted for %s, returning default value",
                    func.__name__,
                )
                return default_on_exhaust

            if last_exception is not None:
                raise last_exception

            raise RuntimeError(f"Unexpected retry state for {func.__name__}")

        return wrapper

    return decorator


def is_retryable_error(
    exception: Exception,
    retryable_codes: Set[int] | None = None,
) -> bool:
    """Check whether an exception is retryable under this policy."""
    codes = retryable_codes or DEFAULT_RETRYABLE_CODES

    if isinstance(exception, ApiException):
        return _extract_api_error_code(exception) in codes
    if isinstance(exception, RetryableBiliApiError):
        return _extract_api_error_code(exception) in codes

    if isinstance(exception, httpx.RequestError):
        return True

    return False
