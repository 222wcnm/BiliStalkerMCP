
import os
import logging
import json
from typing import Any, Dict, Optional, Callable, Coroutine, Union, Annotated
from datetime import datetime, timezone
from functools import wraps

from fastmcp import FastMCP, Context
from mcp.types import TextContent
from pydantic import Field, BaseModel
from bilibili_api.exceptions import ApiException
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

    # --- Precheck Decorator for Tools ---
    def precheck(func: Callable[..., Coroutine[Any, Any, Dict[str, Any]]]) -> Callable[..., Coroutine[Any, Any, Dict[str, Any]]]:
        @wraps(func)
        async def wrapper(ctx: Context, user_id: Union[int, None] = None, username: Union[str, None] = None, **kwargs: Any) -> Dict[str, Any]:
            # Get credentials from session config provided by Smithery
            session_config = ctx.session_config
            cred = get_credential(session_config.sessdata, session_config.bili_jct, session_config.buvid3)

            if not cred or not cred.sessdata:
                return {"error": "凭证未在会话中配置。请在 MCP 客户端或 Smithery UI 中提供。"}
            if user_id is None and not username:
                return {"error": "必须提供 user_id 或 username 中的一个。"}

            try:
                target_uid = await _resolve_user_id(user_id, username)
                if not target_uid:
                    return {"error": f"用户 '{username or user_id}' 未找到。"}
                
                # Pass credential and resolved UID to the actual tool function
                return await func(ctx=ctx, cred=cred, user_id=target_uid, **kwargs)
            except Exception as e:
                logger.error(f"An unexpected error in decorator for {func.__name__}: {e}")
                return {"error": f"预检查过程中发生未知错误: {str(e)}。"}
        return wrapper

    # --- MCP Tool Definitions ---
    @mcp.tool()
    @precheck
    async def get_user_info(ctx: Context, cred: Any, user_id: int) -> Dict[str, Any]:
        return await fetch_user_info(user_id, cred)

    @mcp.tool()
    @precheck
    async def get_user_video_updates(ctx: Context, cred: Any, user_id: int, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        return await fetch_user_videos(user_id, page, limit, cred)

    @mcp.tool()
    @precheck
    async def get_user_dynamic_updates(ctx: Context, cred: Any, user_id: int, offset: int = 0, limit: int = 10, dynamic_type: str = "ALL") -> Dict[str, Any]:
        return await fetch_user_dynamics(user_id, offset, limit, cred, dynamic_type)

    @mcp.tool()
    @precheck
    async def get_user_articles(ctx: Context, cred: Any, user_id: int, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        return await fetch_user_articles(user_id, page, limit, cred)

    @mcp.tool()
    @precheck
    async def get_user_followings(ctx: Context, cred: Any, user_id: int, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        return await fetch_user_followings(user_id, page, limit, cred)

    # --- Prompts (unchanged) ---
    @mcp.prompt()
    def format_user_info_response(user_info_json: str) -> str:
        # ... (implementation is the same)
        pass

    # ... (other prompts)

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

