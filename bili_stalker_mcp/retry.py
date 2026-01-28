"""
统一重试机制模块

提供通用的重试装饰器，支持指数退避策略，用于处理 Bilibili API 的反爬限制（412错误）和网络异常。
"""

import asyncio
import functools
import logging
import random
from typing import Any, Callable, Optional, Set, Type, TypeVar, Union

import httpx
from bilibili_api.exceptions import ApiException

logger = logging.getLogger(__name__)

# 默认可重试的 API 错误码
DEFAULT_RETRYABLE_CODES: Set[int] = {-412, -509}

T = TypeVar('T')


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
    """
    统一重试装饰器，支持指数退避策略。
    
    Args:
        max_retries: 最大重试次数（不包括首次尝试）
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        retryable_codes: 可重试的 API 错误码集合（默认: {-412, -509}）
        retryable_exceptions: 可重试的异常类型元组（默认: httpx.RequestError）
        on_retry: 重试时的回调函数，接收 (attempt, exception) 参数
        default_on_exhaust: 重试耗尽时返回的默认值（仅当 return_default=True 时生效）
        return_default: 重试耗尽时是否返回默认值而非抛出异常
    
    Returns:
        装饰后的异步函数
    
    Example:
        @with_retry(max_retries=3, base_delay=2.0)
        async def fetch_data():
            ...
    """
    if retryable_codes is None:
        retryable_codes = DEFAULT_RETRYABLE_CODES
    
    if retryable_exceptions is None:
        retryable_exceptions = (httpx.RequestError,)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None
            
            for attempt in range(max_retries + 1):
                try:
                    # 非首次尝试时添加随机延迟（反爬策略）
                    if attempt > 0:
                        delay = min(
                            base_delay * (2 ** (attempt - 1)) + random.uniform(0.5, 1.5),
                            max_delay
                        )
                        logger.warning(
                            f"Retry {attempt}/{max_retries} for {func.__name__} "
                            f"in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        # 首次请求也添加小延迟，减少触发反爬概率
                        await asyncio.sleep(random.uniform(0.3, 0.8))
                    
                    return await func(*args, **kwargs)
                
                except ApiException as e:
                    last_exception = e
                    error_code = getattr(e, 'code', None)
                    
                    # 检查是否为可重试的错误码
                    if error_code in retryable_codes:
                        if attempt < max_retries:
                            if on_retry:
                                on_retry(attempt + 1, e)
                            logger.warning(
                                f"API error (code: {error_code}) in {func.__name__}, "
                                f"will retry..."
                            )
                            continue
                        else:
                            logger.error(
                                f"API error (code: {error_code}) in {func.__name__} "
                                f"after {max_retries} retries"
                            )
                    else:
                        # 不可重试的错误码，直接抛出
                        logger.error(f"Non-retryable API error in {func.__name__}: {e}")
                        raise
                
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        if on_retry:
                            on_retry(attempt + 1, e)
                        logger.warning(
                            f"Retryable error in {func.__name__}: {type(e).__name__}, "
                            f"will retry..."
                        )
                        continue
                    else:
                        logger.error(
                            f"Error in {func.__name__} after {max_retries} retries: {e}"
                        )
                
                except Exception as e:
                    # 检查是否为 HTTP 412 错误（可能来自底层库）
                    error_str = str(e)
                    if '412' in error_str:
                        last_exception = e
                        if attempt < max_retries:
                            if on_retry:
                                on_retry(attempt + 1, e)
                            logger.warning(
                                f"HTTP 412 error in {func.__name__}, will retry..."
                            )
                            continue
                        else:
                            logger.error(
                                f"HTTP 412 error in {func.__name__} "
                                f"after {max_retries} retries"
                            )
                    else:
                        # 其他异常直接抛出
                        raise
            
            # 重试耗尽
            if return_default:
                logger.warning(
                    f"All retries exhausted for {func.__name__}, "
                    f"returning default value"
                )
                return default_on_exhaust
            
            if last_exception:
                raise last_exception
            
            # 理论上不会到达这里
            raise RuntimeError(f"Unexpected state in retry wrapper for {func.__name__}")
        
        return wrapper
    
    return decorator


def is_retryable_error(exception: Exception, retryable_codes: Set[int] = None) -> bool:
    """
    判断异常是否可重试。
    
    Args:
        exception: 异常对象
        retryable_codes: 可重试的错误码集合
    
    Returns:
        是否可重试
    """
    if retryable_codes is None:
        retryable_codes = DEFAULT_RETRYABLE_CODES
    
    if isinstance(exception, ApiException):
        return getattr(exception, 'code', None) in retryable_codes
    
    if isinstance(exception, httpx.RequestError):
        return True
    
    # 检查 HTTP 412 错误
    if '412' in str(exception):
        return True
    
    return False
