import httpx
import pytest
from bilibili_api import aid2bvid

from bili_stalker_mcp.errors import (
    InvalidVideoIdentifierError,
    ShortLinkResolutionError,
)
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
@pytest.mark.parametrize(
    "raw",
    [
        "nonsense_string",
        "",
        "  ",
        "BV123",
        "BV1xx411c7mDx",
        "BV1xx411c7m_",
        "prefixBV1xx411c7mD",
        "av170001oops",
        "av0",
    ],
)
async def test_invalid_input_is_rejected(raw):
    with pytest.raises(InvalidVideoIdentifierError):
        await extract_bvid(raw)


@pytest.mark.asyncio
async def test_whitespace_stripped():
    assert await extract_bvid("  BV1xx411c7mD  ") == "BV1xx411c7mD"


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["BV1Ab4y1c7eF", "av170001"])
async def test_short_link_resolved(monkeypatch, identifier):
    redirected_url = f"https://www.bilibili.com/video/{identifier}/"

    class FakeClient:
        async def head(self, url, *, follow_redirects=False):
            return httpx.Response(200, request=httpx.Request("HEAD", redirected_url))

    monkeypatch.setattr(
        "bili_stalker_mcp.utils.video_id_parser.get_shared_http_client",
        lambda: FakeClient(),
    )
    expected = aid2bvid(170001) if identifier.startswith("av") else identifier
    assert await extract_bvid("https://b23.tv/AbCdEfG") == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [httpx.ConnectError("private-url"), httpx.ReadTimeout("private-url")]
)
async def test_short_link_http_error_is_explicit(monkeypatch, error):
    class FakeClient:
        async def head(self, url, *, follow_redirects=False):
            raise error

    monkeypatch.setattr(
        "bili_stalker_mcp.utils.video_id_parser.get_shared_http_client",
        lambda: FakeClient(),
    )
    with pytest.raises(ShortLinkResolutionError) as caught:
        await extract_bvid("https://b23.tv/AbCdEfG")
    assert "private-url" not in str(caught.value)


@pytest.mark.asyncio
async def test_b23_text_on_external_host_does_not_trigger_request(monkeypatch):
    def fail_if_called():
        raise AssertionError("external URL must not be requested")

    monkeypatch.setattr(
        "bili_stalker_mcp.utils.video_id_parser.get_shared_http_client",
        fail_if_called,
    )

    url = "https://example.com/redirect?target=b23.tv"
    with pytest.raises(InvalidVideoIdentifierError):
        await extract_bvid(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,status",
    [
        ("https://www.bilibili.com/", 200),
        ("https://www.bilibili.com/video/BV123", 200),
        ("https://www.bilibili.com/video/BV1xx411c7mD", 404),
        ("https://b23.tv/BV1xx411c7mD", 200),
    ],
)
async def test_short_link_requires_successful_video_destination(
    monkeypatch, url, status
):
    class FakeClient:
        async def head(self, *args, **kwargs):
            return httpx.Response(status, request=httpx.Request("HEAD", url))

    monkeypatch.setattr(
        "bili_stalker_mcp.utils.video_id_parser.get_shared_http_client",
        lambda: FakeClient(),
    )
    with pytest.raises(ShortLinkResolutionError):
        await extract_bvid("https://b23.tv/BV1xx411c7mD")
