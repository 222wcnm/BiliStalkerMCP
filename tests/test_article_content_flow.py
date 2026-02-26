import pytest

from bili_stalker_mcp.services.user_service import fetch_article_content


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
        "id": 42,
        "title": "demo article",
        "markdown_content": "# hello\n\ncontent",
    }


@pytest.mark.asyncio
async def test_fetch_article_content_falls_back_on_unsupported_payload(monkeypatch):
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

    monkeypatch.setattr(
        "bili_stalker_mcp.services.user_service.article.Article", FakeArticle
    )

    result = await fetch_article_content(article_id=44386142, cred=None)

    assert result["id"] == 44386142
    assert result["title"] == "legacy article"
    assert "Full markdown content is unavailable" in result["markdown_content"]
    assert "readInfo" in result["markdown_content"]
    assert (
        "Source: https://www.bilibili.com/video/BV1xx411c7mD"
        in result["markdown_content"]
    )
