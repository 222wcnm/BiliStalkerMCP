
import logging
from typing import Annotated, Any, Dict, Optional, Tuple

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
    get_credential,
)

# --- Smithery Configuration Schema ---
class BiliStalkerConfig(BaseModel):
    sessdata: Optional[str] = Field(None, description="Bilibili SESSDATA cookie for basic authentication (optional, can use environment variables).")
    bili_jct: Optional[str] = Field(None, description="Bilibili BILI_JCT cookie for enhanced authentication (optional).")
    buvid3: Optional[str] = Field(None, description="Bilibili BUVID3 cookie for anti-crawler protection (optional).")

# --- Common Helper Functions ---
def _get_credential_from_context(ctx: Context) -> Tuple[Optional[Credential], Optional[Dict[str, Any]]]:
    """从 Context 配置或环境变量获取凭证
    
    Returns:
        (Credential, None) 如果成功
        (None, error_dict) 如果失败
    """
    config = getattr(ctx, 'config', None)
    sessdata = getattr(config, 'sessdata', None) if config else None
    bili_jct = getattr(config, 'bili_jct', None) if config else None
    buvid3 = getattr(config, 'buvid3', None) if config else None

    # 优先从环境变量获取
    cred = get_credential()
    if not cred and sessdata:
        # 从 Smithery 配置创建凭证
        cred = Credential(sessdata=sessdata, bili_jct=bili_jct or "", buvid3=buvid3 or "")

    if not cred:
        return None, {"error": "Missing SESSDATA configuration. Please provide SESSDATA in Smithery server config or environment variables."}
    
    return cred, None

def _parse_user_identifier(user_id_or_username: str) -> Tuple[Optional[int], Optional[str]]:
    """解析用户标识符
    
    Returns:
        (user_id, None) 如果是数字ID
        (None, username) 如果是用户名
    """
    try:
        return int(user_id_or_username), None
    except ValueError:
        return None, user_id_or_username

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
        user_id_or_username: Annotated[str, Field(description="用户ID（数字）或用户名")]
    ) -> Dict[str, Any]:
        """获取指定哔哩哔哩用户的详细信息"""
        cred, error = _get_credential_from_context(ctx)
        if error:
            return error
        
        user_id, username = _parse_user_identifier(user_id_or_username)
        
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
        user_id_or_username: Annotated[str, Field(description="用户ID（数字）或用户名")],
        page: Annotated[int, Field(description="页码，从1开始")] = 1,
        limit: Annotated[int, Field(description="每页视频数量，最大30")] = 10
    ) -> Dict[str, Any]:
        """获取用户的最新视频更新列表"""
        cred, error = _get_credential_from_context(ctx)
        if error:
            return error
        
        user_id, username = _parse_user_identifier(user_id_or_username)
        
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
        user_id_or_username: Annotated[str, Field(description="用户ID（数字）或用户名")],
        offset: Annotated[int, Field(description="偏移量，从0开始")] = 0,
        limit: Annotated[int, Field(description="获取数量")] = 10,
        dynamic_type: Annotated[str, Field(description="动态类型：ALL(默认,仅文字/图文/转发), ALL_RAW(全部), VIDEO, ARTICLE, DRAW, TEXT")] = "ALL"
    ) -> Dict[str, Any]:
        """获取用户的动态更新
        
        返回的 images 字段包含图片URL列表，可用 ![](url) 格式渲染展示给用户。
        """
        cred, error = _get_credential_from_context(ctx)
        if error:
            return error
        
        user_id, username = _parse_user_identifier(user_id_or_username)
        
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
        user_id_or_username: Annotated[str, Field(description="用户ID（数字）或用户名")],
        page: Annotated[int, Field(description="页码，从1开始")] = 1,
        limit: Annotated[int, Field(description="每页文章数量")] = 10
    ) -> Dict[str, Any]:
        """获取用户的专栏文章列表"""
        cred, error = _get_credential_from_context(ctx)
        if error:
            return error
        
        user_id, username = _parse_user_identifier(user_id_or_username)
        
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
        user_id_or_username: Annotated[str, Field(description="用户ID（数字）或用户名")],
        page: Annotated[int, Field(description="页码，从1开始")] = 1,
        limit: Annotated[int, Field(description="每页关注者数量")] = 20
    ) -> Dict[str, Any]:
        """获取用户关注列表"""
        cred, error = _get_credential_from_context(ctx)
        if error:
            return error
        
        user_id, username = _parse_user_identifier(user_id_or_username)
        
        try:
            target_uid = await _resolve_user_id(user_id, username)
            if not target_uid:
                return {"error": f"用户 '{user_id_or_username}' 未找到。"}
            return await fetch_user_followings(target_uid, page, limit, cred)
        except Exception as e:
            logger.error(f"An error in get_user_followings: {e}")
            return {"error": f"获取用户关注时发生错误: {str(e)}。"}

    return mcp

