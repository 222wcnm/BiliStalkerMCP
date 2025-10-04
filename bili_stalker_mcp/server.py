
import os
import logging
from typing import Any, Dict, Optional

from fastmcp import FastMCP, Context
from pydantic import Field, BaseModel
from smithery.decorators import smithery

from bilibili_api import Credential
from .core import (
    get_user_id_by_username,
    fetch_user_info,
    fetch_user_videos,
    fetch_user_dynamics,
    fetch_user_articles,
    fetch_user_followings,
)
from .config import (
    DynamicType,
)

# --- Smithery Configuration Schema ---
class BiliStalkerConfig(BaseModel):
    sessdata: str = Field(..., description="Bilibili SESSDATA cookie for basic authentication.")
    bili_jct: Optional[str] = Field(None, description="Bilibili BILI_JCT cookie for enhanced authentication (optional).")

# --- Custom Context with Type Hinting for Smithery Config ---
class BiliStalkerContext(Context):
    config: BiliStalkerConfig

# --- Smithery Server Definition ---
@smithery.server(config_schema=BiliStalkerConfig)
def create_server():
    """Create and configure the BiliStalkerMCP server for Smithery."""

    logger = logging.getLogger(__name__)
    mcp = FastMCP("BiliStalkerMCP")

    # --- Internal Helper Functions ---
    async def _resolve_user_id(user_id: int | None, username: str | None) -> int | None:
        if user_id is not None:
            return user_id
        if username:
            return await get_user_id_by_username(username)
        return None

    # --- MCP Tool Definitions ---
    @mcp.tool()
    async def get_user_info(ctx: BiliStalkerContext, user_id_or_username: str) -> Dict[str, Any]:
        """获取指定哔哩哔哩用户的详细信息

        Args:
            user_id_or_username: 用户ID（数字）或用户名
        """
        # Get credentials from the context config provided by Smithery
        if not ctx.config or not ctx.config.sessdata:
            return {"error": "凭证未在配置中提供。请提供 SESSDATA。"}
        
        cred = Credential(sessdata=ctx.config.sessdata, bili_jct=ctx.config.bili_jct)

        # Try to parse as user ID first, then as username
        try:
            # Check if it's an integer user ID
            user_id = int(user_id_or_username)
            username = None
        except ValueError:
            # It's a username string
            user_id = None
            username = user_id_or_username

        try:
            target_uid = await _resolve_user_id(user_id, username)
            if not target_uid:
                return {"error": f"用户 '{user_id_or_username}' 未找到。"}
            return await fetch_user_info(target_uid, cred)
        except Exception as e:
            logger.error(f"An error in get_user_info: {e}")
            return {"error": f"获取用户信息时发生错误: {str(e)}。"}

    @mcp.tool()
    async def get_user_video_updates(ctx: BiliStalkerContext, user_id_or_username: str, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """获取用户的最新视频更新列表

        Args:
            user_id_or_username: 用户ID（数字）或用户名
            page: 页码（从1开始），默认为1
            limit: 每页视频数量（最大30），默认为10
        """
        # Get credentials from the context config provided by Smithery
        if not ctx.config or not ctx.config.sessdata:
            return {"error": "凭证未在配置中提供。请提供 SESSDATA。"}
        
        cred = Credential(sessdata=ctx.config.sessdata, bili_jct=ctx.config.bili_jct)

        # Try to parse as user ID first, then as username
        try:
            user_id = int(user_id_or_username)
            username = None
        except ValueError:
            user_id = None
            username = user_id_or_username

        try:
            target_uid = await _resolve_user_id(user_id, username)
            if not target_uid:
                return {"error": f"用户 '{user_id_or_username}' 未找到。"}
            return await fetch_user_videos(target_uid, page, limit, cred)
        except Exception as e:
            logger.error(f"An error in get_user_video_updates: {e}")
            return {"error": f"获取用户视频时发生错误: {str(e)}。"}

    @mcp.tool()
    async def get_user_dynamic_updates(ctx: BiliStalkerContext, user_id_or_username: str, offset: int = 0, limit: int = 10, dynamic_type: str = "ALL") -> Dict[str, Any]:
        """获取用户的动态更新

        Args:
            user_id_or_username: 用户ID（数字）或用户名
            offset: 偏移量，从0开始
            limit: 获取数量，默认为10
            dynamic_type: 动态类型过滤（ALL, TEXT, IMAGE, VIDEO, ARTICLE）
        """
        # Get credentials from the context config provided by Smithery
        if not ctx.config or not ctx.config.sessdata:
            return {"error": "凭证未在配置中提供。请提供 SESSDATA。"}
        
        cred = Credential(sessdata=ctx.config.sessdata, bili_jct=ctx.config.bili_jct)

        # Try to parse as user ID first, then as username
        try:
            user_id = int(user_id_or_username)
            username = None
        except ValueError:
            user_id = None
            username = user_id_or_username

        try:
            target_uid = await _resolve_user_id(user_id, username)
            if not target_uid:
                return {"error": f"用户 '{user_id_or_username}' 未找到。"}
            return await fetch_user_dynamics(target_uid, offset, limit, cred, dynamic_type)
        except Exception as e:
            logger.error(f"An error in get_user_dynamic_updates: {e}")
            return {"error": f"获取用户动态时发生错误: {str(e)}。"}

    @mcp.tool()
    async def get_user_articles(ctx: BiliStalkerContext, user_id_or_username: str, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """获取用户的专栏文章列表

        Args:
            user_id_or_username: 用户ID（数字）或用户名
            page: 页码，从1开始，默认为1
            limit: 每页文章数量，默认为10
        """
        # Get credentials from the context config provided by Smithery
        if not ctx.config or not ctx.config.sessdata:
            return {"error": "凭证未在配置中提供。请提供 SESSDATA。"}
        
        cred = Credential(sessdata=ctx.config.sessdata, bili_jct=ctx.config.bili_jct)

        # Try to parse as user ID first, then as username
        try:
            user_id = int(user_id_or_username)
            username = None
        except ValueError:
            user_id = None
            username = user_id_or_username

        try:
            target_uid = await _resolve_user_id(user_id, username)
            if not target_uid:
                return {"error": f"用户 '{user_id_or_username}' 未找到。"}
            return await fetch_user_articles(target_uid, page, limit, cred)
        except Exception as e:
            logger.error(f"An error in get_user_articles: {e}")
            return {"error": f"获取用户文章时发生错误: {str(e)}。"}

    @mcp.tool()
    async def get_user_followings(ctx: BiliStalkerContext, user_id_or_username: str, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """获取用户关注列表

        Args:
            user_id_or_username: 用户ID（数字）或用户名
            page: 页码，从1开始，默认为1
            limit: 每页关注者数量，默认为20
        """
        # Get credentials from the context config provided by Smithery
        if not ctx.config or not ctx.config.sessdata:
            return {"error": "凭证未在配置中提供。请提供 SESSDATA。"}
        
        cred = Credential(sessdata=ctx.config.sessdata, bili_jct=ctx.config.bili_jct)

        # Try to parse as user ID first, then as username
        try:
            user_id = int(user_id_or_username)
            username = None
        except ValueError:
            user_id = None
            username = user_id_or_username

        try:
            target_uid = await _resolve_user_id(user_id, username)
            if not target_uid:
                return {"error": f"用户 '{user_id_or_username}' 未找到。"}
            return await fetch_user_followings(target_uid, page, limit, cred)
        except Exception as e:
            logger.error(f"An error in get_user_followings: {e}")
            return {"error": f"获取用户关注时发生错误: {str(e)}。"}



    return mcp
