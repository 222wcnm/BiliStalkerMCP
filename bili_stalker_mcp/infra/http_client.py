import httpx

from ..config import CONNECT_TIMEOUT, READ_TIMEOUT

_http_client: httpx.AsyncClient | None = None


def get_shared_http_client() -> httpx.AsyncClient:
    global _http_client

    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
        )
    return _http_client


async def close_shared_http_client() -> None:
    """Close and reset the shared HTTP client."""
    global _http_client

    client = _http_client
    _http_client = None

    if client is not None and not client.is_closed:
        await client.aclose()
