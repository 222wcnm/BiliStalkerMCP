import asyncio

import httpx
import pytest
from bilibili_api import aid2bvid

from bili_stalker_mcp.errors import (
    InvalidSubtitleSelectionError,
    InvalidVideoIdentifierError,
    ShortLinkResolutionError,
)
from bili_stalker_mcp.observability import begin_request, snapshot_metrics
from bili_stalker_mcp.utils import video_id_parser
from bili_stalker_mcp.utils.video_id_parser import extract_bvid, extract_video_reference


@pytest.fixture(autouse=True)
def isolate_short_link_cache(monkeypatch):
    video_id_parser._resolve_short_link_cached.cache_clear()
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MODE", "never")
    yield
    video_id_parser._resolve_short_link_cached.cache_clear()


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
    assert calls == [("https://b23.tv/AbCdEfG", False)]


@pytest.mark.asyncio
async def test_short_link_stops_at_video_location_and_caches_page(monkeypatch):
    calls = []

    class FakeClient:
        async def head(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(
                302,
                headers={"Location": "https://www.bilibili.com/video/BV1xx411c7mD?p=2"},
                request=httpx.Request("HEAD", url),
            )

    monkeypatch.setattr(video_id_parser, "get_shared_http_client", lambda: FakeClient())
    begin_request("short-link-first")
    first = await extract_video_reference("https://b23.tv/AbCdEfG")
    assert first.bvid == "BV1xx411c7mD" and first.page == 2
    assert snapshot_metrics()["upstream_call_count"] == 1
    begin_request("short-link-cached")
    assert await extract_video_reference("https://b23.tv/AbCdEfG") == first
    assert len(calls) == 1
    assert calls[0][1]["follow_redirects"] is False
    assert snapshot_metrics()["upstream_call_count"] == 0
    assert snapshot_metrics()["cache"]["short_link"]["hit"] == 1


@pytest.mark.asyncio
async def test_short_link_follows_only_needed_relative_hop(monkeypatch):
    calls = []

    class FakeClient:
        async def head(self, url, **_kwargs):
            calls.append(url)
            location = (
                "/next"
                if len(calls) == 1
                else "https://m.bilibili.com/video/av170001?p=3"
            )
            return httpx.Response(302, headers={"Location": location})

    monkeypatch.setattr(video_id_parser, "get_shared_http_client", lambda: FakeClient())
    result = await extract_video_reference("https://b23.tv/AbCdEfG")
    assert result.bvid == aid2bvid(170001) and result.page == 3
    assert calls == ["https://b23.tv/AbCdEfG", "https://b23.tv/next"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location",
    [
        "https://evilbilibili.com/video/BV1xx411c7mD",
        "https://bilibili.com.evil.test/video/BV1xx411c7mD",
        "http://127.0.0.1/video/BV1xx411c7mD",
        "file:///video/BV1xx411c7mD",
        "https://private@www.bilibili.com/video/BV1xx411c7mD",
        "https://b23.tv/AbCdEfG",
    ],
)
async def test_short_link_rejects_unsafe_redirect_or_loop(monkeypatch, location):
    calls = []

    class FakeClient:
        async def head(self, url, **_kwargs):
            calls.append(url)
            return httpx.Response(302, headers={"Location": location})

    monkeypatch.setattr(video_id_parser, "get_shared_http_client", lambda: FakeClient())
    with pytest.raises(ShortLinkResolutionError):
        await extract_bvid("https://b23.tv/AbCdEfG")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_short_link_limits_redirect_count(monkeypatch):
    calls = []

    class FakeClient:
        async def head(self, url, **_kwargs):
            calls.append(url)
            return httpx.Response(302, headers={"Location": f"/next{len(calls)}"})

    monkeypatch.setattr(video_id_parser, "get_shared_http_client", lambda: FakeClient())
    with pytest.raises(ShortLinkResolutionError):
        await extract_bvid("https://b23.tv/AbCdEfG")
    assert len(calls) == 5


@pytest.mark.asyncio
async def test_short_link_timeout_cancels_request_without_caching_failure(monkeypatch):
    cancelled = asyncio.Event()
    calls = []

    class FakeClient:
        async def head(self, url, **_kwargs):
            calls.append(url)
            if len(calls) == 1:
                try:
                    await asyncio.sleep(10)
                finally:
                    cancelled.set()
            return httpx.Response(
                302, headers={"Location": "https://www.bilibili.com/video/BV1xx411c7mD"}
            )

    monkeypatch.setattr(video_id_parser, "SHORT_LINK_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(video_id_parser, "get_shared_http_client", lambda: FakeClient())
    with pytest.raises(ShortLinkResolutionError):
        await extract_bvid("https://b23.tv/AbCdEfG")
    assert cancelled.is_set()
    assert await extract_bvid("https://b23.tv/AbCdEfG") == "BV1xx411c7mD"
    assert len(calls) == 2
