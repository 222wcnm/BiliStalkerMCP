import logging
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from ..config import (
    CONNECT_TIMEOUT,
    DEFAULT_HEADERS,
    DEFAULT_IMPERSONATE,
    READ_TIMEOUT,
    REQUEST_TIMEOUT,
)
from ..observability import record_upstream_block, record_upstream_rate_limit
from ..retry import RetryableBiliApiError
from .upstream import timed_upstream_call

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised indirectly in runtime environments
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - fallback path for environments without curl_cffi
    curl_requests = None


RETRYABLE_HTTP_STATUSES = {403, 412, 429}

_http_client: "SharedRawHttpClient | None" = None


def build_cookie_header(cred: Any | None) -> str:
    if cred is None or not hasattr(cred, "get_cookies"):
        return ""

    try:
        cookies = cred.get_cookies() or {}
    except Exception:
        return ""

    return "; ".join(f"{key}={value}" for key, value in cookies.items() if value)


def build_request_headers(
    *,
    cred: Any | None = None,
    headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    merged_headers = DEFAULT_HEADERS.copy()
    if headers:
        merged_headers.update({key: value for key, value in headers.items() if value is not None})

    if "Cookie" not in merged_headers:
        cookie_header = build_cookie_header(cred)
        if cookie_header:
            merged_headers["Cookie"] = cookie_header

    return merged_headers


def _is_bilibili_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return False

    return hostname.endswith(
        (
            "bilibili.com",
            "b23.tv",
            "hdslb.com",
            "bilivideo.com",
        )
    )


def _build_http_status_error(
    *,
    method: str,
    url: str,
    status_code: int,
    text: str = "",
) -> httpx.HTTPStatusError:
    request = httpx.Request(method.upper(), url)
    response = httpx.Response(status_code=status_code, request=request, text=text)
    message = f"{status_code} response while requesting {url}"
    return httpx.HTTPStatusError(message, request=request, response=response)


def _raise_for_retryable_status(status_code: int, url: str) -> None:
    if status_code == 429:
        record_upstream_rate_limit()
        raise RetryableBiliApiError(
            code=status_code,
            message=f"HTTP rate limit from upstream for {url}",
        )

    if status_code in {403, 412}:
        record_upstream_block()
        raise RetryableBiliApiError(
            code=status_code,
            message=f"HTTP anti-bot block from upstream for {url}",
        )


class SharedRawHttpClient:
    def __init__(self) -> None:
        self._httpx_client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS.copy(),
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
        )
        self._curl_session = None
        self._closed = False

        if curl_requests is not None:
            self._curl_session = curl_requests.AsyncSession(
                headers=DEFAULT_HEADERS.copy(),
                timeout=REQUEST_TIMEOUT,
                impersonate=DEFAULT_IMPERSONATE,
                raise_for_status=False,
            )
        else:
            logger.debug("curl_cffi is unavailable, raw requests will use httpx fallback only")

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        if self._closed:
            raise RuntimeError("Shared HTTP client is closed")

        request_kwargs = dict(kwargs)
        follow_redirects = request_kwargs.pop("follow_redirects", None)

        if _is_bilibili_url(url) and self._curl_session is not None:
            if follow_redirects is not None:
                request_kwargs["allow_redirects"] = follow_redirects
            return await self._curl_session.request(
                method.upper(),
                url,
                impersonate=DEFAULT_IMPERSONATE,
                **request_kwargs,
            )

        if follow_redirects is not None:
            request_kwargs["follow_redirects"] = follow_redirects
        return await self._httpx_client.request(method.upper(), url, **request_kwargs)

    async def get(self, url: str, **kwargs: Any) -> Any:
        return await self.request("GET", url, **kwargs)

    async def head(self, url: str, **kwargs: Any) -> Any:
        return await self.request("HEAD", url, **kwargs)

    async def aclose(self) -> None:
        if self._closed:
            return

        self._closed = True
        await self._httpx_client.aclose()

        if self._curl_session is not None:
            await self._curl_session.close()


def get_shared_http_client() -> SharedRawHttpClient:
    global _http_client

    if _http_client is None or _http_client.is_closed:
        _http_client = SharedRawHttpClient()
    return _http_client


async def close_shared_http_client() -> None:
    """Close and reset the shared HTTP client."""
    global _http_client

    client = _http_client
    _http_client = None

    if client is not None and not client.is_closed:
        await client.aclose()


async def request_json(
    url: str,
    *,
    method: str = "GET",
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    cred: Any | None = None,
    follow_redirects: bool = True,
    timeout: float = REQUEST_TIMEOUT,
) -> dict[str, Any]:
    client = get_shared_http_client()
    merged_headers = build_request_headers(cred=cred, headers=headers)
    method_name = method.upper()

    if method_name == "GET":
        response = await timed_upstream_call(
            client.get(
                url,
                params=params,
                headers=merged_headers,
                follow_redirects=follow_redirects,
                timeout=timeout,
            )
        )
    else:
        response = await timed_upstream_call(
            client.request(
                method_name,
                url,
                params=params,
                headers=merged_headers,
                follow_redirects=follow_redirects,
                timeout=timeout,
            )
        )

    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code in RETRYABLE_HTTP_STATUSES:
        _raise_for_retryable_status(status_code, url)
    if status_code >= 400:
        raise _build_http_status_error(
            method=method_name,
            url=url,
            status_code=status_code,
            text=str(getattr(response, "text", "")),
        )

    try:
        payload = response.json()
    except Exception as exc:  # pragma: no cover - defensive against malformed upstream payloads
        raise ValueError(f"Invalid JSON response from {url}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected JSON response type from {url}: {type(payload).__name__}")

    return payload


async def get_json(
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    cred: Any | None = None,
    follow_redirects: bool = True,
    timeout: float = REQUEST_TIMEOUT,
) -> dict[str, Any]:
    return await request_json(
        url,
        method="GET",
        params=params,
        headers=headers,
        cred=cred,
        follow_redirects=follow_redirects,
        timeout=timeout,
    )
