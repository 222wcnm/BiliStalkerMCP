import httpx
import pytest
from bilibili_api import aid2bvid

from bili_stalker_mcp.utils.video_id_parser import extract_bvid


@pytest.mark.asyncio
async def test_pure_bvid():
    assert await extract_bvid("BV1xx411c7mD") == "BV1xx411c7mD"


@pytest.mark.asyncio
async def test_bvid_from_standard_url():
    assert (
        await extract_bvid("https://www.bilibili.com/video/BV1xx411c7mD/")
        == "BV1xx411c7mD"
    )


@pytest.mark.asyncio
async def test_bvid_from_url_with_params():
    result = await extract_bvid(
        "https://www.bilibili.com/video/BV1xx411c7mD/?p=2&vd_source=abc"
    )
    assert result == "BV1xx411c7mD"


@pytest.mark.asyncio
async def test_bvid_from_mobile_url():
    assert (
        await extract_bvid("https://m.bilibili.com/video/BV1xx411c7mD")
        == "BV1xx411c7mD"
    )


@pytest.mark.asyncio
async def test_av_number():
    expected = aid2bvid(170001)
    assert await extract_bvid("av170001") == expected


@pytest.mark.asyncio
async def test_av_number_from_url():
    expected = aid2bvid(170001)
    assert await extract_bvid("https://www.bilibili.com/video/av170001/") == expected


@pytest.mark.asyncio
async def test_unrecognized_input_returned_unchanged():
    assert await extract_bvid("nonsense_string") == "nonsense_string"


@pytest.mark.asyncio
async def test_whitespace_stripped():
    assert await extract_bvid("  BV1xx411c7mD  ") == "BV1xx411c7mD"


@pytest.mark.asyncio
async def test_empty_string_returned_unchanged():
    assert await extract_bvid("") == ""


@pytest.mark.asyncio
async def test_short_link_resolved(monkeypatch):
    redirected_url = "https://www.bilibili.com/video/BV1Ab4y1c7eF/"

    class FakeResponse:
        url = httpx.URL(redirected_url)

    class FakeClient:
        async def head(self, url, *, follow_redirects=False):
            return FakeResponse()

    monkeypatch.setattr(
        "bili_stalker_mcp.utils.video_id_parser.get_shared_http_client",
        lambda: FakeClient(),
    )
    assert await extract_bvid("https://b23.tv/AbCdEfG") == "BV1Ab4y1c7eF"


@pytest.mark.asyncio
async def test_short_link_http_error_returns_original(monkeypatch):
    class FakeClient:
        async def head(self, url, *, follow_redirects=False):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        "bili_stalker_mcp.utils.video_id_parser.get_shared_http_client",
        lambda: FakeClient(),
    )
    assert await extract_bvid("https://b23.tv/AbCdEfG") == "https://b23.tv/AbCdEfG"


@pytest.mark.asyncio
async def test_b23_text_on_external_host_does_not_trigger_request(monkeypatch):
    def fail_if_called():
        raise AssertionError("external URL must not be requested")

    monkeypatch.setattr(
        "bili_stalker_mcp.utils.video_id_parser.get_shared_http_client",
        fail_if_called,
    )

    url = "https://example.com/redirect?target=b23.tv"
    assert await extract_bvid(url) == url
