import pytest
from fastmcp.exceptions import ToolError

from bili_stalker_mcp import server as server_module
from bili_stalker_mcp.services import user_service


@pytest.fixture(autouse=True)
def clear_user_search_caches():
    user_service._search_users_cached.cache_clear()
    yield
    user_service._search_users_cached.cache_clear()


@pytest.mark.asyncio
async def test_search_users_returns_lightweight_candidates_and_exact_uid(monkeypatch):
    calls = 0

    async def fake_search_by_type(**kwargs):
        nonlocal calls
        calls += 1
        assert kwargs["keyword"] == "Fraternidad邓"
        assert kwargs["page_size"] == 20
        return {
            "result": [
                {
                    "mid": "123",
                    "uname": "Other user",
                    "usign": "other sign",
                    "upic": "https://example.com/other.jpg",
                    "fans": 5,
                    "videos": 2,
                    "level": 3,
                    "is_live": False,
                },
                {
                    "mid": 456,
                    "uname": "Fraternidad邓",
                    "usign": "target sign",
                    "upic": "https://example.com/target.jpg",
                    "fans": "99",
                    "videos": "12",
                    "level": "6",
                    "is_live": True,
                },
            ]
        }

    monkeypatch.setattr(user_service.search, "search_by_type", fake_search_by_type)

    result = await user_service.search_users(" Fraternidad邓 ", limit=10)
    resolved = await user_service.get_user_id_by_username("Fraternidad邓")

    assert calls == 1
    assert result == {
        "users": [
            {
                "uid": 123,
                "name": "Other user",
                "sign": "other sign",
                "avatar": "https://example.com/other.jpg",
                "follower": 5,
                "videos": 2,
                "level": 3,
                "is_live": False,
                "is_exact_match": False,
            },
            {
                "uid": 456,
                "name": "Fraternidad邓",
                "sign": "target sign",
                "avatar": "https://example.com/target.jpg",
                "follower": 99,
                "videos": 12,
                "level": 6,
                "is_live": True,
                "is_exact_match": True,
            },
        ],
        "count": 2,
        "exact_match_uid": 456,
    }
    assert resolved == 456


@pytest.mark.asyncio
async def test_username_resolution_does_not_fall_back_to_first_candidate(monkeypatch):
    async def fake_search_by_type(**_kwargs):
        return {"result": [{"mid": 123, "uname": "Similar user"}]}

    monkeypatch.setattr(user_service.search, "search_by_type", fake_search_by_type)

    result = await user_service.get_user_id_by_username("Target user")

    assert result is None


@pytest.mark.asyncio
async def test_user_search_timeout_is_retried_once_then_raised(monkeypatch):
    calls = 0

    async def fake_timed_upstream_call(_awaitable):
        nonlocal calls
        calls += 1
        raise TimeoutError

    def fake_search_by_type(**_kwargs):
        return {}

    monkeypatch.setattr(user_service.search, "search_by_type", fake_search_by_type)
    monkeypatch.setattr(user_service, "timed_upstream_call", fake_timed_upstream_call)

    with pytest.raises(TimeoutError):
        await user_service.search_users("slow user")

    assert calls == 2


@pytest.mark.asyncio
async def test_search_users_tool_does_not_require_credentials(monkeypatch):
    async def fail_if_credentials_are_loaded(_ctx):
        pytest.fail("search_users must not load user credentials")

    async def fake_search_users(keyword, limit):
        assert keyword == "target"
        assert limit == 5
        return {"users": [], "count": 0, "exact_match_uid": None}

    monkeypatch.setattr(
        server_module,
        "_get_credential_from_context",
        fail_if_credentials_are_loaded,
    )
    monkeypatch.setattr(server_module, "search_users_service", fake_search_users)
    tools = {
        tool.name: tool for tool in await server_module.create_server().list_tools()
    }

    result = await tools["search_users"].fn(keyword="target", limit=5)

    assert result == {"users": [], "count": 0, "exact_match_uid": None}


@pytest.mark.asyncio
async def test_search_users_tool_returns_actionable_timeout(monkeypatch):
    async def fake_search_users(_keyword, _limit):
        raise TimeoutError

    monkeypatch.setattr(server_module, "search_users_service", fake_search_users)
    tools = {
        tool.name: tool for tool in await server_module.create_server().list_tools()
    }

    with pytest.raises(ToolError, match="search timed out"):
        await tools["search_users"].fn(keyword="target")
