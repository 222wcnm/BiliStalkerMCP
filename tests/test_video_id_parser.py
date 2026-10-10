import httpx
import pytest
from bilibili_api import aid2bvid

from bili_stalker_mcp.errors import (
    InvalidSubtitleSelectionError,
    InvalidVideoIdentifierError,
    ShortLinkResolutionError,
)
from bili_stalker_mcp.utils.video_id_parser import extract_bvid, extract_video_reference


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw,page",
    [
        ("BV1xx411c7mD", None),
        ("https://www.bilibili.com/video/BV1xx411c7mD/?p=2&vd_source=abc", 2),
        ("https://m.bilibili.com/video/BV1xx411c7mD?p=3", 3),
        ("https://www.bilibili.com/video/av170001?p=2", 2),
    ],
)
async def test_video_reference_preserves_url_page(raw, page):
    reference = await extract_video_reference(raw)
    assert reference.bvid == (aid2bvid(170001) if "av170001" in raw else "BV1xx411c7mD")
    assert reference.page == page


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["p=0", "p=-1", "p=oops", "p=", "p=1.5", "p=2&p=3"])
async def test_invalid_url_page_is_rejected_without_changing_identifier_only_parser(
    query,
):
    raw = f"https://www.bilibili.com/video/BV1xx411c7mD?{query}&vd_source=private-token"
    with pytest.raises(InvalidSubtitleSelectionError) as caught:
        await extract_video_reference(raw)
    assert "private-token" not in str(caught.value)
    assert "https://" not in str(caught.value)
    assert await extract_bvid(raw) == "BV1xx411c7mD"


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["BV1xx411c7mD", "av170001"])
async def test_video_reference_resolves_short_link_once_and_keeps_destination_page(
    monkeypatch, identifier
):
    calls = []
    redirected_url = f"https://www.bilibili.com/video/{identifier}/?p=2"

    class FakeClient:
        async def head(self, url, *, follow_redirects=False):
            calls.append((url, follow_redirects))
            return httpx.Response(200, request=httpx.Request("HEAD", redirected_url))

    monkeypatch.setattr(
        "bili_stalker_mcp.utils.video_id_parser.get_shared_http_client",
        lambda: FakeClient(),
    )
    reference = await extract_video_reference("https://b23.tv/AbCdEfG")
    assert reference.bvid == (
        aid2bvid(170001) if identifier.startswith("av") else identifier
    )
    assert reference.page == 2
    assert calls == [("https://b23.tv/AbCdEfG", True)]
