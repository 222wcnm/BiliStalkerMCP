import pytest
from bilibili_api.exceptions import ApiException, ResponseCodeException

from bili_stalker_mcp.services.user_service import (
    _legacy_cv_markdown,
    fetch_article_content,
)


@pytest.mark.asyncio
async def test_fetch_article_content_calls_fetch_content_before_markdown(monkeypatch):
    calls: list[str] = []

    class FakeArticle:
        def __init__(self, cvid, credential):
            self.cvid = cvid
            self.credential = credential
            self._loaded = False

        async def get_info(self):
            calls.append("get_info")
            return {"title": "demo article"}

        async def fetch_content(self):
            calls.append("fetch_content")
            self._loaded = True

        def markdown(self):
            calls.append("markdown")
            if not self._loaded:
                raise RuntimeError("fetch_content not called")
            return "# hello\n\ncontent"

    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service.article.Article", FakeArticle
    )

    result = await fetch_article_content(article_id=42, cred=None)

    assert calls == ["get_info", "fetch_content", "markdown"]
    assert result == {
        "id": "42",
        "title": "demo article",
        "markdown_content": "# hello\n\ncontent",
    }


@pytest.mark.asyncio
async def test_fetch_article_content_parses_opus_initial_state_when_readinfo_missing(
    monkeypatch,
):
    class FakeArticle:
        def __init__(self, cvid, credential):
            self.cvid = cvid
            self.credential = credential

        async def get_info(self):
            return {"title": "legacy article"}

        async def fetch_content(self):
            raise KeyError("readInfo")

        def markdown(self):
            raise RuntimeError("should not be called")

    async def fake_get_initial_state(url, credential):
        assert "cv44386142" in url
        return (
            {
                "detail": {
                    "basic": {"title": "state title"},
                    "modules": [
                        {
                            "module_content": {
                                "paragraphs": [
                                    {
                                        "para_type": 1,
                                        "text": {
                                            "nodes": [
                                                {
                                                    "type": "TEXT_NODE_TYPE_WORD",
                                                    "word": {
                                                        "words": "第一段",
                                                        "style": {"bold": True},
                                                    },
                                                }
                                            ]
                                        },
                                    },
                                    {
                                        "para_type": 1,
                                        "text": {
                                            "nodes": [
                                                {
                                                    "type": "TEXT_NODE_TYPE_RICH",
                                                    "rich": {
                                                        "text": "网页链接",
                                                        "jump_url": "https://example.com/a",
                                                    },
                                                }
                                            ]
                                        },
                                    },
                                    {
                                        "para_type": 2,
                                        "pic": {
                                            "pics": [
                                                {"url": "https://example.com/image.png"}
                                            ]
                                        },
                                    },
                                ]
                            }
                        }
                    ],
                }
            },
            object(),
        )

    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service.article.Article", FakeArticle
    )
    monkeypatch.setattr(
        "bili_stalker_mcp.services.article_renderer.get_initial_state",
        fake_get_initial_state,
    )

    result = await fetch_article_content(article_id=44386142, cred=None)

    assert result["id"] == "44386142"
    assert result["title"] == "legacy article"
    assert result["markdown_content"].startswith("# legacy article")
    assert "**第一段**" in result["markdown_content"]
    assert "[网页链接](https://example.com/a)" in result["markdown_content"]
    assert "![](https://example.com/image.png)" in result["markdown_content"]


@pytest.mark.asyncio
async def test_fetch_article_content_keeps_fallback_when_initial_state_also_fails(
    monkeypatch,
):
    class FakeArticle:
        def __init__(self, cvid, credential):
            self.cvid = cvid
            self.credential = credential

        async def get_info(self):
            return {
                "title": "legacy article",
                "video_url": "https://www.bilibili.com/video/BV1xx411c7mD",
            }

        async def fetch_content(self):
            raise KeyError("readInfo")

        def markdown(self):
            raise RuntimeError("should not be called")

    async def fake_get_initial_state(url, credential):
        raise RuntimeError("blocked")

    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service.article.Article", FakeArticle
    )
    monkeypatch.setattr(
        "bili_stalker_mcp.services.article_renderer.get_initial_state",
        fake_get_initial_state,
    )

    result = await fetch_article_content(article_id=44386142, cred=None)

    assert result["id"] == "44386142"
    assert result["title"] == "legacy article"
    assert "Full markdown content is unavailable" in result["markdown_content"]
    assert "readInfo" in result["markdown_content"]
    assert (
        "Source: https://www.bilibili.com/video/BV1xx411c7mD"
        in result["markdown_content"]
    )


@pytest.mark.asyncio
async def test_legacy_cv_markdown_reraises_retryable_api_errors(monkeypatch):
    """Rate-limit / anti-bot errors must propagate so @with_retry can handle them.

    Without re-raising, a transient -509 / -412 / 429 from the legacy SDK would
    be silently converted into a fallback markdown response, masking the outage.
    """

    class FakeArticle:
        def __init__(self, cvid, credential):
            self.cvid = cvid
            self.credential = credential

        async def get_info(self):
            return {"title": "rate-limited article"}

        async def fetch_content(self):
            # -509 is a retryable rate-limit code per DEFAULT_RETRYABLE_CODES.
            raise ResponseCodeException(code=-509, msg="Request is rate-limited")

        def markdown(self):
            raise RuntimeError("should not be called")

    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service.article.Article", FakeArticle
    )

    with pytest.raises(ResponseCodeException):
        await _legacy_cv_markdown(cvid=12345, cred=None)


@pytest.mark.asyncio
async def test_legacy_cv_markdown_handles_api_exception_with_broken_str(monkeypatch):
    class FakeArticle:
        def __init__(self, cvid, credential):
            self.cvid = cvid
            self.credential = credential

        async def get_info(self):
            return {"title": "legacy article"}

        async def fetch_content(self):
            raise ApiException({"code": -400, "message": "bad request"})

    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service.article.Article", FakeArticle
    )

    info, markdown, error_reason = await _legacy_cv_markdown(cvid=12345, cred=None)

    assert info == {"title": "legacy article"}
    assert markdown is None
    assert error_reason is not None
    assert "ApiException" in error_reason


# ── opus snowflake ID path tests ──────────────────────────────────────

# A representative opus snowflake ID (>= 2^53) used across the tests below.
_OPUS_SNOWFLAKE_ID = 748254891671027745


@pytest.mark.asyncio
async def test_opus_id_skips_legacy_parser_and_uses_opus_payload(monkeypatch):
    """Opus snowflake IDs (>= 2^53) must bypass the legacy cv parser entirely
    and fetch content via the opus page payload."""

    legacy_called = False

    original_legacy = _legacy_cv_markdown

    async def spy_legacy(*args, **kwargs):
        nonlocal legacy_called
        legacy_called = True
        return await original_legacy(*args, **kwargs)

    async def fake_get_initial_state(url, credential):
        # The URL must be the opus-style URL, not the cv-style URL.
        assert f"/opus/{_OPUS_SNOWFLAKE_ID}" in url
        assert "read/cv" not in url
        return (
            {
                "detail": {
                    "basic": {
                        "title": "opus article title",
                        "rid_str": str(_OPUS_SNOWFLAKE_ID),
                    },
                    "modules": [
                        {
                            "module_content": {
                                "paragraphs": [
                                    {
                                        "para_type": 1,
                                        "text": {
                                            "nodes": [
                                                {
                                                    "type": "TEXT_NODE_TYPE_WORD",
                                                    "word": {
                                                        "words": "Opus content body",
                                                        "style": {},
                                                    },
                                                }
                                            ]
                                        },
                                    },
                                ]
                            }
                        }
                    ],
                }
            },
            object(),
        )

    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service._legacy_cv_markdown", spy_legacy
    )
    monkeypatch.setattr(
        "bili_stalker_mcp.services.article_renderer.get_initial_state",
        fake_get_initial_state,
    )

    result = await fetch_article_content(article_id=_OPUS_SNOWFLAKE_ID, cred=None)

    assert not legacy_called, "Legacy cv parser should NOT be called for opus IDs"
    assert result["id"] == str(_OPUS_SNOWFLAKE_ID)
    assert result["title"] == "opus article title"
    assert "Opus content body" in result["markdown_content"]


@pytest.mark.asyncio
async def test_opus_id_falls_back_when_opus_payload_fails(monkeypatch):
    """When an opus snowflake ID is used but the opus page extraction fails,
    the result should be a fallback markdown instead of raising."""

    async def fake_get_initial_state(url, credential):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(
        "bili_stalker_mcp.services.article_renderer.get_initial_state",
        fake_get_initial_state,
    )

    result = await fetch_article_content(article_id=_OPUS_SNOWFLAKE_ID, cred=None)

    assert result["id"] == str(_OPUS_SNOWFLAKE_ID)
    assert "Full markdown content is unavailable" in result["markdown_content"]
    assert "upstream payload unavailable" in result["markdown_content"]


@pytest.mark.asyncio
async def test_opus_id_accepted_as_string(monkeypatch):
    """Opus snowflake IDs passed as strings (the typical MCP tool input) must
    work identically to integer input."""

    async def fake_get_initial_state(url, credential):
        assert f"/opus/{_OPUS_SNOWFLAKE_ID}" in url
        return (
            {
                "detail": {
                    "basic": {"title": "string-id article"},
                    "modules": [
                        {
                            "module_content": {
                                "paragraphs": [
                                    {
                                        "para_type": 1,
                                        "text": {
                                            "nodes": [
                                                {
                                                    "type": "TEXT_NODE_TYPE_WORD",
                                                    "word": {
                                                        "words": "Body text",
                                                        "style": {},
                                                    },
                                                }
                                            ]
                                        },
                                    },
                                ]
                            }
                        }
                    ],
                }
            },
            object(),
        )

    monkeypatch.setattr(
        "bili_stalker_mcp.services.article_renderer.get_initial_state",
        fake_get_initial_state,
    )

    # Pass as string -- this is what the MCP tool layer sends after server.py validation.
    result = await fetch_article_content(article_id=str(_OPUS_SNOWFLAKE_ID), cred=None)

    assert result["id"] == str(_OPUS_SNOWFLAKE_ID)
    assert result["title"] == "string-id article"
    assert "Body text" in result["markdown_content"]
