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
        content_type = schema["properties"]["content_type"]
        assert content_type["type"] == "string"
        assert content_type["enum"] == expected_types
        assert "content_type" in schema["required"]


@pytest.mark.asyncio
async def test_comment_tools_expose_stable_paging_contract():
    tools = {tool.name: tool for tool in await create_server().list_tools()}

    comments_schema = tools["get_content_comments"].parameters
    replies_schema = tools["get_content_comment_replies"].parameters

    assert comments_schema["properties"]["limit"]["default"] == 20
    assert comments_schema["properties"]["limit"]["maximum"] == 20
    assert comments_schema["properties"]["sort"]["default"] == "hot"
    assert comments_schema["properties"]["sort"]["enum"] == ["hot", "time"]

    assert replies_schema["properties"]["page"]["default"] == 1
    assert replies_schema["properties"]["page"]["maximum"] == 1000
    assert replies_schema["properties"]["limit"]["default"] == 20
    assert replies_schema["properties"]["limit"]["maximum"] == 20
