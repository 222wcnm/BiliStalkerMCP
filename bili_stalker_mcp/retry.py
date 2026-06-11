"""Unified retry strategy for transient Bilibili/API network failures."""

import asyncio
import functools
import logging
import random
from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    Set,
    Type,
    TypeVar,
    cast,
)

import httpx
from bilibili_api.exceptions import ApiException, NetworkException

from .observability import add_retry

logger = logging.getLogger(__name__)

DEFAULT_RETRYABLE_CODES: Set[int] = {-412, -509, 403, 412, 429}

AsyncCallable = TypeVar("AsyncCallable", bound=Callable[..., Awaitable[Any]])


class RetryableBiliApiError(Exception):
    """Structured error carrying a Bilibili code for retry classification."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{message} (code={code})")


def _extract_api_error_code(exc: Exception) -> int | None:
    """Best-effort extraction of Bilibili API error code from an exception.

    Handles three exception families:
    - ``RetryableBiliApiError`` – project-level sentinel (``.code``).
    - ``ResponseCodeException`` / generic ``ApiException`` – (``.code``).
    - ``NetworkException`` – HTTP-level status (``.status``).
    """
    if isinstance(exc, RetryableBiliApiError):
        return exc.code

    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code

    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status

    if exc.args:
        first = exc.args[0]
        if isinstance(first, dict):
            arg_code = first.get("code")
            if isinstance(arg_code, int):
                return arg_code

    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code

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
) -> Callable[[AsyncCallable], AsyncCallable]:
    """Retry async call with exponential backoff on deterministic transient failures."""
    codes = DEFAULT_RETRYABLE_CODES if retryable_codes is None else retryable_codes
    exceptions = (
        (httpx.RequestError,) if retryable_exceptions is None else retryable_exceptions
    )

    def decorator(func: AsyncCallable) -> AsyncCallable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            retry_exhausted = False

            for attempt in range(max_retries + 1):
                try:
                    # First attempt is immediate. Backoff applies only to retries.
                    if attempt > 0:
                        delay = min(
                            base_delay * (2 ** (attempt - 1))
                            + random.uniform(0.0, 0.5),
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

                except (ApiException, NetworkException, RetryableBiliApiError) as exc:
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
                        retry_exhausted = True
                        logger.error(
                            "Retryable API error exhausted in %s (code=%s)",
                            func.__name__,
                            code,
                        )
                    else:
                        logger.error(
                            "Non-retryable API error in %s (code=%s): %r",
                            func.__name__,
                            code,
                            exc,
                        )
                    break

                except httpx.HTTPStatusError as exc:
                    last_exception = exc
                    code = _extract_api_error_code(exc)
                    if code in codes and attempt < max_retries:
                        add_retry()
                        if on_retry:
                            on_retry(attempt + 1, exc)
                        logger.warning(
                            "Retryable HTTP status in %s (status=%s)",
                            func.__name__,
                            code,
                        )
                        continue
                    if code in codes:
                        retry_exhausted = True
                        logger.error(
                            "Retryable HTTP status exhausted in %s (status=%s)",
                            func.__name__,
                            code,
                        )
                    else:
                        logger.error(
                            "Non-retryable HTTP status in %s (status=%s): %s",
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
                    retry_exhausted = True
                    break

            if return_default and retry_exhausted:
                logger.warning(
                    "All retries exhausted for %s, returning default value",
                    func.__name__,
                )
                return default_on_exhaust

            if last_exception is not None:
                raise last_exception

            raise RuntimeError(f"Unexpected retry state for {func.__name__}")

        return cast(AsyncCallable, wrapper)

    return decorator


def is_retryable_error(
    exception: Exception,
    retryable_codes: Set[int] | None = None,
) -> bool:
    """Check whether an exception is retryable under this policy."""
    codes = retryable_codes or DEFAULT_RETRYABLE_CODES

    if isinstance(exception, (ApiException, NetworkException, RetryableBiliApiError)):
        return _extract_api_error_code(exception) in codes

    if isinstance(exception, httpx.HTTPStatusError):
        return _extract_api_error_code(exception) in codes

    if isinstance(exception, httpx.RequestError):
        return True

    return False
