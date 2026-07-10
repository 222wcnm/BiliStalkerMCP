import pytest

from bili_stalker_mcp.server import create_server


async def _tool_schemas():
    return {tool.name: tool.parameters for tool in await create_server().list_tools()}


@pytest.mark.asyncio
async def test_dynamic_tool_exposes_expected_dynamic_type_contract():
    schemas = await _tool_schemas()

    dynamic_type = schemas["get_user_dynamics"]["properties"]["dynamic_type"]

    assert dynamic_type["type"] == "string"
    assert dynamic_type["default"] == "ALL"
    assert dynamic_type["enum"] == [
        "ALL",
        "ALL_RAW",
        "VIDEO",
        "ARTICLE",
        "DRAW",
        "TEXT",
    ]


@pytest.mark.asyncio
async def test_video_detail_exposes_expected_subtitle_mode_contract():
    schemas = await _tool_schemas()

    subtitle_mode = schemas["get_video_detail"]["properties"]["subtitle_mode"]
    subtitle_max_chars = schemas["get_video_detail"]["properties"]["subtitle_max_chars"]

    assert subtitle_mode["type"] == "string"
    assert subtitle_mode["default"] == "smart"
    assert subtitle_mode["enum"] == ["minimal", "smart", "full"]
    assert subtitle_max_chars["minimum"] == 1
    assert subtitle_max_chars["maximum"] == 200000


@pytest.mark.asyncio
async def test_public_tool_limit_bounds_are_stable():
    schemas = await _tool_schemas()

    expected_limit_maximums = {
        "get_user_videos": 30,
        "search_user_videos": 30,
        "get_user_dynamics": 30,
        "get_user_articles": 30,
        "get_user_followings": 50,
        "get_content_comments": 20,
        "get_content_comment_replies": 20,
    }

    for tool_name, expected_maximum in expected_limit_maximums.items():
        limit = schemas[tool_name]["properties"]["limit"]
        assert limit["type"] == "integer"
        assert limit["minimum"] == 1
        assert limit["maximum"] == expected_maximum
