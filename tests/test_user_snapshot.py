import asyncio

import pytest

from bili_stalker_mcp import server as server_module


@pytest.fixture(autouse=True)
def fake_credential(monkeypatch):
    async def _fake_credential(_ctx):
        return None

    monkeypatch.setattr(
        server_module, "_get_credential_from_context", _fake_credential
    )


async def _snapshot_tool():
    tools = {
        tool.name: tool for tool in await server_module.create_server().list_tools()
    }
    return tools["get_user_snapshot"]


@pytest.mark.asyncio
async def test_user_snapshot_fetches_sections_concurrently(monkeypatch):
    in_flight = {"current": 0, "max": 0}

    async def _tracked(payload):
        in_flight["current"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["current"])
        await asyncio.sleep(0.01)
        in_flight["current"] -= 1
        return payload

    async def fake_user_info(uid, cred):
        return await _tracked({"mid": uid, "name": "demo"})

    async def fake_videos(uid, page, limit, cred, **kwargs):
        assert (page, limit) == (1, 5)
        return await _tracked({"videos": [], "total": 0})

    async def fake_dynamics(*, user_id, limit, cred, dynamic_type, cursor):
        assert (limit, dynamic_type, cursor) == (10, "ALL", None)
        return await _tracked({"dynamics": []})

    async def fake_articles(uid, page, limit, cred):
        return await _tracked({"articles": [], "total": 0})

    monkeypatch.setattr(server_module, "fetch_user_info", fake_user_info)
    monkeypatch.setattr(server_module, "fetch_user_videos", fake_videos)
    monkeypatch.setattr(server_module, "fetch_user_dynamics", fake_dynamics)
    monkeypatch.setattr(server_module, "fetch_user_articles", fake_articles)

    tool = await _snapshot_tool()
    result = await tool.fn(
        ctx=None,
        user_id_or_username="12345",
        video_limit=5,
        dynamic_limit=10,
        article_limit=10,
    )

    assert result["uid"] == 12345
    assert result["user"] == {"mid": 12345, "name": "demo"}
    assert result["videos"] == {"videos": [], "total": 0}
    assert result["dynamics"] == {"dynamics": []}
    assert result["articles"] == {"articles": [], "total": 0}
    assert result["errors"] == {}
    assert in_flight["max"] == 4


@pytest.mark.asyncio
async def test_user_snapshot_reports_partial_failures_and_skips_sections(monkeypatch):
    async def fake_user_info(uid, cred):
        return {"mid": uid}

    async def fake_videos(uid, page, limit, cred, **kwargs):
        raise RuntimeError("upstream exploded")

    async def fake_dynamics(**kwargs):
        pytest.fail("dynamics must be skipped when dynamic_limit=0")

    async def fake_articles(uid, page, limit, cred):
        return {"articles": []}

    monkeypatch.setattr(server_module, "fetch_user_info", fake_user_info)
    monkeypatch.setattr(server_module, "fetch_user_videos", fake_videos)
    monkeypatch.setattr(server_module, "fetch_user_dynamics", fake_dynamics)
    monkeypatch.setattr(server_module, "fetch_user_articles", fake_articles)

    tool = await _snapshot_tool()
    result = await tool.fn(
        ctx=None,
        user_id_or_username="777",
        dynamic_limit=0,
    )

    assert result["user"] == {"mid": 777}
    assert result["videos"] is None
    assert result["dynamics"] is None
    assert result["articles"] == {"articles": []}
    assert set(result["errors"]) == {"videos"}
