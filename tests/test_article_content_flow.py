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
        "bili_stalker_mcp.services.user_service.get_initial_state",
        fake_get_initial_state,
    )

    result = await fetch_article_content(article_id=44386142, cred=None)

    assert result["id"] == 44386142
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
        "bili_stalker_mcp.services.user_service.get_initial_state",
        fake_get_initial_state,
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
