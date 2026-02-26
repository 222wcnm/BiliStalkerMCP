import pytest

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
