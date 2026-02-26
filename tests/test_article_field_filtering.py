from datetime import datetime

import pytest

from bili_stalker_mcp.services.user_service import fetch_user_articles


@pytest.mark.asyncio
async def test_fetch_user_articles_filters_stats_to_whitelist(monkeypatch):
    class FakeUser:
        def __init__(self, uid, credential):
            self.uid = uid
            self.credential = credential

        async def get_articles(self, pn, ps):
            assert pn == 1
            assert ps == 2
            return {
                "articles": [
                    {
                        "id": "1001",
                        "title": "article-1",
                        "summary": "summary-1",
                        "publish_time": 1700000000,
                        "stats": {
                            "view": "100",
                            "like": 20,
                            "reply": "30",
                            "coin": 40,
                            "share": "50",
                            "favorite": 60,
                            "dynamic": 70,
                            "series": 80,
                            "series_id": 90,
                        },
                    }
                ],
                "count": 12,
            }

    monkeypatch.setattr("bili_stalker_mcp.services.user_service.user.User", FakeUser)

    result = await fetch_user_articles(user_id=1, page=1, limit=2, cred=None)

    assert set(result.keys()) == {"articles", "total"}
    assert result["total"] == 12
    assert len(result["articles"]) == 1

    article = result["articles"][0]
    assert set(article.keys()) == {
        "id",
        "title",
        "summary",
        "publish_time_str",
        "stats",
    }
    assert article["id"] == 1001
    datetime.strptime(article["publish_time_str"], "%Y-%m-%d %H:%M")

    stats = article["stats"]
    assert set(stats.keys()) == {"view", "like", "reply", "coin", "share"}
    assert stats == {
        "view": 100,
        "like": 20,
        "reply": 30,
        "coin": 40,
        "share": 50,
    }
    assert "favorite" not in stats
    assert "series" not in stats
