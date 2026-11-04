from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bili_stalker_mcp.infra import http_client
from bili_stalker_mcp.infra.http_client import (
    close_shared_http_client,
    get_shared_http_client,
)


@pytest.mark.asyncio
async def test_shared_http_client_can_be_closed_and_recreated():
    client_1 = get_shared_http_client()
    client_2 = get_shared_http_client()
    assert client_1 is client_2
    assert client_1.is_closed is False

    await close_shared_http_client()
    assert client_1.is_closed is True

    client_3 = get_shared_http_client()
    assert client_3 is not client_1
    assert client_3.is_closed is False

    await close_shared_http_client()


@pytest.mark.asyncio
async def test_curl_request_does_not_initialize_unused_httpx(monkeypatch):
    curl = SimpleNamespace(
        request=AsyncMock(return_value="response"), close=AsyncMock()
    )
    monkeypatch.setattr(
        http_client,
        "curl_requests",
        SimpleNamespace(AsyncSession=lambda **_kwargs: curl),
    )
    monkeypatch.setattr(
        http_client,
        "_build_httpx_client",
        lambda *_args: pytest.fail("unused HTTPX initialized"),
    )
    client = http_client.SharedRawHttpClient()
    assert (
        await client.head("https://b23.tv/example", follow_redirects=False)
        == "response"
    )
    assert curl.request.call_args.kwargs["allow_redirects"] is False
    await client.aclose()
    await client.aclose()
    curl.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("curl_available", [False, True])
async def test_httpx_is_created_on_first_use_and_reused(monkeypatch, curl_available):
    curl = SimpleNamespace(request=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(
        http_client,
        "curl_requests",
        (
            SimpleNamespace(AsyncSession=lambda **_kwargs: curl)
            if curl_available
            else None
        ),
    )
    fallback = SimpleNamespace(
        request=AsyncMock(return_value="response"), aclose=AsyncMock()
    )
    constructed = []

    def build(proxy):
        constructed.append(proxy)
        return fallback

    monkeypatch.setattr(http_client, "_build_httpx_client", build)
    client = http_client.SharedRawHttpClient()
    assert constructed == []
    for _ in range(2):
        assert (
            await client.get("https://example.com/", follow_redirects=True)
            == "response"
        )
    assert len(constructed) == 1
    assert fallback.request.call_args.kwargs["follow_redirects"] is True
    assert curl.request.await_count == 0
    await client.aclose()
    fallback.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_still_releases_curl_when_httpx_close_fails(monkeypatch):
    curl = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(
        http_client,
        "curl_requests",
        SimpleNamespace(AsyncSession=lambda **_kwargs: curl),
    )
    client = http_client.SharedRawHttpClient()
    client._httpx_client = SimpleNamespace(
        aclose=AsyncMock(side_effect=RuntimeError("close failed"))
    )
    with pytest.raises(RuntimeError, match="close failed"):
        await client.aclose()
    curl.close.assert_awaited_once()
