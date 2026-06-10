import pytest

from bili_stalker_mcp.server import create_server


@pytest.mark.asyncio
async def test_only_generic_comment_tools_are_exposed():
    tools = {tool.name: tool for tool in await create_server().list_tools()}

    assert "get_content_comments" in tools
    assert "get_content_comment_replies" in tools
    assert "get_video_comments" not in tools
    assert "get_video_comment_replies" not in tools


@pytest.mark.asyncio
async def test_comment_tools_expose_content_type_enum():
    tools = {tool.name: tool for tool in await create_server().list_tools()}

    expected_types = ["video", "article", "dynamic"]
    for tool_name in ("get_content_comments", "get_content_comment_replies"):
        schema = tools[tool_name].parameters
        assert schema["properties"]["content_type"]["enum"] == expected_types
