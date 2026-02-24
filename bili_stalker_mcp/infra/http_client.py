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
