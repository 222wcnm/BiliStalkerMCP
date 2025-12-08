
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
    sessdata: Optional[str] = Field(None, description="Bilibili SESSDATA cookie for basic authentication (optional, can use environment variables).")
    bili_jct: Optional[str] = Field(None, description="Bilibili BILI_JCT cookie for enhanced authentication (optional).")
    buvid3: Optional[str] = Field(None, description="Bilibili BUVID3 cookie for anti-crawler protection (optional).")

# --- Note: Using standard Context as smithery decorator handles config injection ---

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

    # --- MCP Prompts ---
    @mcp.prompt()
    def track_user_updates() -> str:
        """跟踪B站用户更新

        这个提示帮助你设置一个自动化工作流来跟踪指定B站用户的最新动态。
        可以获取用户的视频、文章、动态等更新内容。
        """
        return """
你是一个B站内容追踪助手。请按照以下步骤帮助用户跟踪目标B站用户的更新：

1. **获取用户基本信息**
   - 使用 get_user_info 工具获取用户详细信息
   - 验证用户是否存在并获取用户ID

2. **获取最新内容更新**
   - 使用 get_user_video_updates 获取最新视频
   - 使用 get_user_dynamic_updates 获取最新动态
   - 使用 get_user_articles 获取最新专栏文章

3. **整理更新信息**
   - 按时间顺序排列更新内容
   - 提供内容摘要和链接
   - 识别重要更新和高价值内容

4. **建议后续行动**
   - 推荐值得关注的视频或文章
   - 提供内容质量评估
   - 建议进一步了解的领域

请用户提供想要跟踪的用户ID或用户名，开始追踪流程。
        """

    @mcp.prompt()
    def analyze_user_activity() -> str:
        """分析B站用户活动模式

        这个提示帮助你深入分析B站用户的活动规律、内容偏好和互动模式。
        """
        return """
你是一个B站用户行为分析专家。请使用以下工具和方法分析用户活动模式：

1. **获取用户基础数据**
   - 使用 get_user_info 获取用户基本信息
   - 使用 get_user_video_updates 获取视频发布历史
   - 使用 get_user_dynamic_updates 获取动态活动
   - 使用 get_user_articles 获取专栏文章

2. **分析发布模式**
   - 内容发布频率和时间段
   - 内容类型分布（视频、动态、文章）
   - 内容质量和受欢迎程度

3. **分析互动行为**
   - 评论和点赞数据
   - 与其他用户的互动模式
   - 社区参与度

4. **生成洞察报告**
   - 用户活跃度评估
   - 内容偏好分析
   - 最佳互动时机建议

5. **提供优化建议**
   - 内容发布策略建议
   - 社区互动优化方案
   - 增长潜力评估

请提供目标用户ID，开始全面分析。
        """

    # --- MCP Resources ---
    @mcp.resource("bili://user/{user_id}/info")
    def get_user_info_resource(user_id: str) -> str:
        """获取B站用户基本信息的资源"""
        return f"""B站用户基本信息资源

用户ID: {user_id}

使用方法:
1. 调用 get_user_info 工具，传入用户ID或用户名
2. 获取用户的详细资料，包括：
   - 用户名和头像
   - 粉丝数和关注数
   - 等级和认证信息
   - 个人简介
   - 账号状态

示例: get_user_info("{user_id}")
"""

    @mcp.resource("bili://user/{user_id}/videos")
    def get_user_videos_resource(user_id: str) -> str:
        """获取B站用户视频资源的资源"""
        return f"""B站用户视频资源

用户ID: {user_id}

使用方法:
1. 调用 get_user_video_updates 工具，传入用户ID或用户名
2. 可选参数:
   - page: 页码（从1开始）
   - limit: 每页视频数量（最大30）

获取内容包括:
- 视频标题和封面
- 发布时间
- 播放量、点赞数、收藏数
- 视频简介和标签
- BV号和播放链接

示例: get_user_video_updates("{user_id}", page=1, limit=10)
"""

    @mcp.resource("bili://user/{user_id}/dynamics")
    def get_user_dynamics_resource(user_id: str) -> str:
        """获取B站用户动态资源的资源"""
        return f"""B站用户动态资源

用户ID: {user_id}

使用方法:
1. 调用 get_user_dynamic_updates 工具，传入用户ID或用户名
2. 可选参数:
   - offset: 偏移量（从0开始）
   - limit: 获取数量
   - dynamic_type: 动态类型（ALL, VIDEO, ARTICLE, ANIME, DRAW）

动态类型说明:
- ALL: 所有动态
- VIDEO: 视频动态
- ARTICLE: 专栏动态
- ANIME: 番剧动态
- DRAW: 图文动态

示例: get_user_dynamic_updates("{user_id}", offset=0, limit=10, dynamic_type="ALL")
"""

    @mcp.resource("bili://user/{user_id}/articles")
    def get_user_articles_resource(user_id: str) -> str:
        """获取B站用户专栏文章资源的资源"""
        return f"""B站用户专栏文章资源

用户ID: {user_id}

使用方法:
1. 调用 get_user_articles 工具，传入用户ID或用户名
2. 可选参数:
   - page: 页码（从1开始）
   - limit: 每页文章数量

获取内容包括:
- 文章标题和封面
- 发布时间
- 阅读量、点赞数、收藏数
- 文章摘要
- 文章链接

示例: get_user_articles("{user_id}", page=1, limit=10)
"""

    @mcp.resource("bili://user/{user_id}/followings")
    def get_user_followings_resource(user_id: str) -> str:
        """获取B站用户关注列表资源的资源"""
        return f"""B站用户关注列表资源

用户ID: {user_id}

使用方法:
1. 调用 get_user_followings 工具，传入用户ID或用户名
2. 可选参数:
   - page: 页码（从1开始）
   - limit: 每页关注数量

获取内容包括:
- 关注用户的ID和用户名
- 头像和简介
- 关注时间
- 认证信息

示例: get_user_followings("{user_id}", page=1, limit=20)
"""

    # --- MCP Tool Definitions ---
    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True
        }
    )
    async def get_user_info(
        ctx: Context,
        user_id_or_username: str
    ) -> Dict[str, Any]:
        """获取指定哔哩哔哩用户的详细信息

        Args:
            user_id_or_username: 用户ID（数字）或用户名。可以是数字ID（如 123456789）或用户名（如 "username"）
        """
        # Get credentials from the context config provided by Smithery
        config = getattr(ctx, 'config', None)
        sessdata = getattr(config, 'sessdata', None) if config else None
        bili_jct = getattr(config, 'bili_jct', None) if config else None
        buvid3 = getattr(config, 'buvid3', None) if config else None

        # Fallback to environment variables if Smithery config is not available
        from .core import get_credential
        cred = get_credential()
        if not cred and sessdata:
            # Manually create credential from Smithery config
            cred = Credential(sessdata=sessdata, bili_jct=bili_jct or "", buvid3=buvid3 or "")

        if not cred:
            return {"error": "Missing SESSDATA configuration. Please provide SESSDATA in Smithery server config or environment variables. Some features may not work without authentication."}

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

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True
        }
    )
    async def get_user_video_updates(
        ctx: Context,
        user_id_or_username: str,
        page: int = 1,
        limit: int = 10
    ) -> Dict[str, Any]:
        """获取用户的最新视频更新列表

        Args:
            user_id_or_username: 用户ID（数字）或用户名。可以是数字ID（如 123456789）或用户名（如 "username"）
            page: 页码（从1开始），默认为1，用于分页获取视频
            limit: 每页视频数量（最大30），默认为10，控制返回的视频数量
        """
        # Get credentials from the context config provided by Smithery
        config = getattr(ctx, 'config', None)
        sessdata = getattr(config, 'sessdata', None) if config else None
        bili_jct = getattr(config, 'bili_jct', None) if config else None
        buvid3 = getattr(config, 'buvid3', None) if config else None

        # Fallback to environment variables if Smithery config is not available
        from .core import get_credential
        cred = get_credential()
        if not cred and sessdata:
            # Manually create credential from Smithery config
            cred = Credential(sessdata=sessdata, bili_jct=bili_jct or "", buvid3=buvid3 or "")

        if not cred:
            return {"error": "Missing SESSDATA configuration. Please provide SESSDATA in Smithery server config or environment variables. Some features may not work without authentication."}

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

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True
        }
    )
    async def get_user_dynamic_updates(
        ctx: Context,
        user_id_or_username: str,
        offset: int = 0,
        limit: int = 10,
        dynamic_type: str = "ALL"
    ) -> Dict[str, Any]:
        """获取用户的动态更新

        Args:
            user_id_or_username: 用户ID（数字）或用户名。可以是数字ID（如 123456789）或用户名（如 "username"）
            offset: 偏移量，从0开始，用于跳过指定数量的动态
            limit: 获取数量，默认为10，控制返回的动态数量
            dynamic_type: 动态类型过滤，可选值：ALL, VIDEO, ARTICLE, ANIME, DRAW，默认为"ALL"
        """
        # Get credentials from the context config provided by Smithery
        config = getattr(ctx, 'config', None)
        sessdata = getattr(config, 'sessdata', None) if config else None
        bili_jct = getattr(config, 'bili_jct', None) if config else None
        buvid3 = getattr(config, 'buvid3', None) if config else None

        # Fallback to environment variables if Smithery config is not available
        from .core import get_credential
        cred = get_credential()
        if not cred and sessdata:
            # Manually create credential from Smithery config
            cred = Credential(sessdata=sessdata, bili_jct=bili_jct or "", buvid3=buvid3 or "")

        if not cred:
            return {"error": "Missing SESSDATA configuration. Please provide SESSDATA in Smithery server config or environment variables. Some features may not work without authentication."}

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

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True
        }
    )
    async def get_user_articles(
        ctx: Context,
        user_id_or_username: str,
        page: int = 1,
        limit: int = 10
    ) -> Dict[str, Any]:
        """获取用户的专栏文章列表

        Args:
            user_id_or_username: 用户ID（数字）或用户名。可以是数字ID（如 123456789）或用户名（如 "username"）
            page: 页码，从1开始，默认为1，用于分页获取文章
            limit: 每页文章数量，默认为10，控制返回的文章数量
        """
        # Get credentials from the context config provided by Smithery
        config = getattr(ctx, 'config', None)
        sessdata = getattr(config, 'sessdata', None) if config else None
        bili_jct = getattr(config, 'bili_jct', None) if config else None

        # Fallback to environment variables if Smithery config is not available
        from .core import get_credential
        cred = get_credential()
        if not cred and sessdata:
            # Manually create credential from Smithery config
            cred = Credential(sessdata=sessdata, bili_jct=bili_jct or "")

        if not cred:
            return {"error": "Missing SESSDATA configuration. Please provide SESSDATA in Smithery server config or environment variables. Some features may not work without authentication."}

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

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True
        }
    )
    async def get_user_followings(
        ctx: Context,
        user_id_or_username: str,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """获取用户关注列表

        Args:
            user_id_or_username: 用户ID（数字）或用户名。可以是数字ID（如 123456789）或用户名（如 "username"）
            page: 页码，从1开始，默认为1，用于分页获取关注列表
            limit: 每页关注者数量，默认为20，控制返回的关注者数量
        """
        # Get credentials from the context config provided by Smithery
        config = getattr(ctx, 'config', None)
        sessdata = getattr(config, 'sessdata', None) if config else None
        bili_jct = getattr(config, 'bili_jct', None) if config else None

        # Fallback to environment variables if Smithery config is not available
        from .core import get_credential
        cred = get_credential()
        if not cred and sessdata:
            # Manually create credential from Smithery config
            cred = Credential(sessdata=sessdata, bili_jct=bili_jct or "")

        if not cred:
            return {"error": "Missing SESSDATA configuration. Please provide SESSDATA in Smithery server config or environment variables. Some features may not work without authentication."}

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
