
import os
import logging
from typing import Any, Dict, Optional, Union
from datetime import datetime

from fastmcp import FastMCP, Context
from pydantic import Field, BaseModel
from smithery.decorators import smithery

from .core import (
    get_credential,
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
    sessdata: str = Field(..., description="Bilibili SESSDATA cookie for authentication.")
    bili_jct: str = Field(..., description="Bilibili BILI_JCT cookie for authentication.")
    buvid3: str = Field(..., description="Bilibili BUVID3 cookie for authentication.")

# --- Smithery Server Definition ---
@smithery.server(config_schema=BiliStalkerConfig)
def create_server():
    """Create and configure the BiliStalkerMCP server for Smithery."""

    logger = logging.getLogger(__name__)
    mcp = FastMCP("BiliStalkerMCP")

    # --- Internal Helper Functions ---
    def _format_timestamp(timestamp: Optional[int]) -> str:
        if timestamp is None:
            return "未知时间"
        try:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%d %H:%M')
        except (ValueError, TypeError, OSError) as e:
            logger.warning(f"时间戳转换失败: {timestamp}, 错误: {e}")
            return f"时间戳错误({timestamp})"

    async def _resolve_user_id(user_id: Union[int, None], username: Union[str, None]) -> Union[int, None]:
        if user_id is not None:
            return user_id
        if username:
            return await get_user_id_by_username(username)
        return None

    # --- MCP Tool Definitions ---
    @mcp.tool()
    async def get_user_info(ctx: Context, user_id_or_username: str) -> Dict[str, Any]:
        """获取指定哔哩哔哩用户的详细信息

        Args:
            user_id_or_username: 用户ID（数字）或用户名
        """
        # Get credentials from session config provided by Smithery
        session_config = ctx.session_config  # type: ignore[attr-defined]
        cred = get_credential(session_config.sessdata, session_config.bili_jct, session_config.buvid3)

        if not cred or not cred.sessdata:
            return {"error": "凭证未在会话中配置。请在 MCP 客户端或 Smithery UI 中提供。"}

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
    async def get_user_video_updates(ctx: Context, user_id_or_username: str, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """获取用户的最新视频更新列表

        Args:
            user_id_or_username: 用户ID（数字）或用户名
            page: 页码（从1开始），默认为1
            limit: 每页视频数量（最大30），默认为10
        """
        # Get credentials from session config provided by Smithery
        session_config = ctx.session_config  # type: ignore[attr-defined]
        cred = get_credential(session_config.sessdata, session_config.bili_jct, session_config.buvid3)

        if not cred or not cred.sessdata:
            return {"error": "凭证未在会话中配置。请在 MCP 客户端或 Smithery UI 中提供。"}

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
    async def get_user_dynamic_updates(ctx: Context, user_id_or_username: str, offset: int = 0, limit: int = 10, dynamic_type: str = "ALL") -> Dict[str, Any]:
        """获取用户的动态更新

        Args:
            user_id_or_username: 用户ID（数字）或用户名
            offset: 偏移量，从0开始
            limit: 获取数量，默认为10
            dynamic_type: 动态类型过滤（ALL, TEXT, IMAGE, VIDEO, ARTICLE）
        """
        # Get credentials from session config provided by Smithery
        session_config = ctx.session_config  # type: ignore[attr-defined]
        cred = get_credential(session_config.sessdata, session_config.bili_jct, session_config.buvid3)

        if not cred or not cred.sessdata:
            return {"error": "凭证未在会话中配置。请在 MCP 客户端或 Smithery UI 中提供。"}

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
    async def get_user_articles(ctx: Context, user_id_or_username: str, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """获取用户的专栏文章列表

        Args:
            user_id_or_username: 用户ID（数字）或用户名
            page: 页码，从1开始，默认为1
            limit: 每页文章数量，默认为10
        """
        # Get credentials from session config provided by Smithery
        session_config = ctx.session_config  # type: ignore[attr-defined]
        cred = get_credential(session_config.sessdata, session_config.bili_jct, session_config.buvid3)

        if not cred or not cred.sessdata:
            return {"error": "凭证未在会话中配置。请在 MCP 客户端或 Smithery UI 中提供。"}

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
    async def get_user_followings(ctx: Context, user_id_or_username: str, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """获取用户关注列表

        Args:
            user_id_or_username: 用户ID（数字）或用户名
            page: 页码，从1开始，默认为1
            limit: 每页关注者数量，默认为20
        """
        # Get credentials from session config provided by Smithery
        session_config = ctx.session_config  # type: ignore[attr-defined]
        cred = get_credential(session_config.sessdata, session_config.bili_jct, session_config.buvid3)

        if not cred or not cred.sessdata:
            return {"error": "凭证未在会话中配置。请在 MCP 客户端或 Smithery UI 中提供。"}

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

# --- Local Development Entry Point (for cli.py) ---
def run_local():
    """Runs the server locally using environment variables, bypassing Smithery decorator."""
    logger = logging.getLogger(__name__)
    mcp = FastMCP("BiliStalkerMCP")

    SESSDATA = os.environ.get("SESSDATA", "")
    BILI_JCT = os.environ.get("BILI_JCT", "")
    BUVID3 = os.environ.get("BUVID3", "")
    cred = get_credential(SESSDATA, BILI_JCT, BUVID3)

    # ... (This would require duplicating all tool definitions outside the create_server function)
    # For simplicity, we will adjust cli.py to use a different approach.
    logger.info("Local run mode has changed. Please use 'uv run dev' or 'uv run playground' as per Smithery docs.")
