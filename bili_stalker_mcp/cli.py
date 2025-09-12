import os
import logging
import json
from typing import Any, Dict, Optional
from datetime import datetime

from fastmcp import FastMCP
from mcp.types import TextContent
from bilibili_api.exceptions import ApiException

from .core import (
    get_credential,
    get_user_id_by_username,
    fetch_user_info,
    fetch_user_videos,
    fetch_user_dynamics,
    fetch_user_articles,
)
from .config import (
    SCHEMAS_URI,
    DynamicType,
)

# --- 初始化 ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

mcp = FastMCP("BiliStalkerMCP")

# 从环境变量获取凭证
SESSDATA = os.environ.get("SESSDATA", "")
BILI_JCT = os.environ.get("BILI_JCT", "")
BUVID3 = os.environ.get("BUVID3", "")
cred = get_credential(SESSDATA, BILI_JCT, BUVID3)

# --- 内部辅助函数 ---
async def _resolve_user_id(user_id: Optional[int], username: Optional[str]) -> Optional[int]:
    """根据user_id或username解析最终的用户ID"""
    if user_id:
        return user_id
    if username:
        return await get_user_id_by_username(username)
    return None

# --- MCP工具定义 ---
@mcp.tool()
async def get_user_info(user_id: Optional[int] = None, username: Optional[str] = None) -> Dict[str, Any]:
    """获取B站用户的详细资料。返回JSON对象，为保证数据完整，默认返回所有字段。"""
    if not cred:
        return {"error": "Credential is not configured."}
    if not user_id and not username:
        return {"error": "Either user_id or username must be provided."}

    try:
        target_uid = await _resolve_user_id(user_id, username)
        if not target_uid:
            return {"error": "User not found."}

        user_info = await fetch_user_info(target_uid, cred)
        return user_info
    except Exception as e:
        logger.error(f"An unexpected error in get_user_info: {e}")
        return {"error": f"An unexpected error occurred: {e}"}


@mcp.tool()
async def get_user_video_updates(user_id: Optional[int] = None, username: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """获取用户的视频列表。'subtitle'字段包含字幕对象，其'subtitles'列表内含可用于文本分析的字幕URL。"""
    if not cred:
        return {"error": "Credential is not configured."}
    if not user_id and not username:
        return {"error": "Either user_id or username must be provided."}
    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}

    try:
        target_uid = await _resolve_user_id(user_id, username)
        if not target_uid:
            return {"error": "User not found."}

        video_data = await fetch_user_videos(target_uid, limit, cred)
        return video_data
    except Exception as e:
        logger.error(f"An unexpected error in get_user_video_updates: {e}")
        return {"error": f"An unexpected error occurred: {e}"}

@mcp.tool()
async def get_user_dynamic_updates(user_id: Optional[int] = None, username: Optional[str] = None, limit: int = 10, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """获取用户的动态列表。为保证数据可用性，返回JSON列表。会尝试解析不同类型的动态。"""
    if not cred:
        return {"error": "Credential is not configured. Please set SESSDATA, BILI_JCT, and BUVID3 environment variables."}
    if not user_id and not username:
        return {"error": "Either user_id or username must be provided."}
    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}
    if dynamic_type not in DynamicType.VALID_TYPES:
        return {"error": f"Invalid dynamic_type. Must be one of {DynamicType.VALID_TYPES}"}

    try:
        target_uid = await _resolve_user_id(user_id, username)
        if not target_uid:
            return {"error": f"User '{username or user_id}' not found. Please check the username or user ID."}

        dynamic_data = await fetch_user_dynamics(target_uid, limit, cred, dynamic_type)
        return dynamic_data
    except Exception as e:
        logger.error(f"An unexpected error in get_user_dynamic_updates: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}."}


@mcp.tool()
async def get_user_articles(user_id: Optional[int] = None, username: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """获取用户的专栏文章列表。为保证数据完整，默认返回所有字段。"""
    if not cred:
        return {"error": "Credential is not configured. Please set SESSDATA, BILI_JCT, and BUVID3 environment variables."}
    if not user_id and not username:
        return {"error": "Either user_id or username must be provided."}
    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}

    try:
        target_uid = await _resolve_user_id(user_id, username)
        if not target_uid:
            return {"error": f"User '{username or user_id}' not found. Please check the username or user ID."}

        article_data = await fetch_user_articles(target_uid, limit, cred)
        return article_data
    except Exception as e:
        logger.error(f"An unexpected error in get_user_articles: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}."}


# --- 提示预设 (用于规范模型输出格式) ---
@mcp.prompt()
def format_video_response(videos_json: str) -> str:
    """格式化视频数据为Markdown, 支持get_user_video_updates工具的输出"""
    try:
        data = json.loads(videos_json)
        video_list = data.get("videos", [])
        if not video_list:
            return "用户最近没有发布新视频。"
        
        md = "### 最新视频\n\n"
        for v in video_list:
            md += f"#### [{v.get('title', '无标题')}]({v.get('url')})\n"
            if v.get('pic'):
                md += f"![cover]({v['pic']})\n\n"
            md += f"- **播放**: {v.get('play', 0)} | **点赞**: {v.get('like', 0)} | **发布于**: {datetime.fromtimestamp(v.get('created')).strftime('%Y-%m-%d')}\n\n"
        return md
    except Exception as e:
        return f"格式化视频数据时出错: {e}"


@mcp.prompt()
def format_dynamic_response(dynamics_json: str) -> str:
    """格式化动态数据为Markdown, 支持get_user_dynamic_updates工具的输出"""
    try:
        data = json.loads(dynamics_json)
        dynamic_list = data.get("dynamics", [])
        if not dynamic_list:
            return "用户最近没有发布新动态。"

        md = "### 最新动态\n\n"
        for d in dynamic_list:
            md += f"**类型**: {d.get('type')} | **发布于**: {datetime.fromtimestamp(d.get('timestamp')).strftime('%Y-%m-%d %H:%M')}"
            md += f"> {d.get('text_content', '')}\n\n"
            if d.get('images'):
                md += " ".join([f"![image]({img})" for img in d['images']]) + "\n\n"
            md += "---"
        return md
    except Exception as e:
        return f"格式化动态数据时出错: {e}"

@mcp.prompt()
def format_articles_response(articles_json: str) -> str:
    """格式化专栏文章数据为Markdown, 支持get_user_articles工具的输出"""
    try:
        data = json.loads(articles_json)
        article_list = data.get("articles", [])
        if not article_list:
            return "用户最近没有发布新专栏文章。"

        md = "### 最新专栏文章\n\n"
        for a in article_list:
            md += f"#### [{a.get('title', '无标题')}]({a.get('url')})\n"
            if a.get('banner_url'):
                md += f"![banner]({a['banner_url']})\n\n"
            md += f"- **阅读**: {a.get('stats', {}).get('view', 0)} | **发布于**: {datetime.fromtimestamp(a.get('publish_time')).strftime('%Y-%m-%d')}"
            md += f"> {a.get('summary', '无摘要')}\n\n"
        return md
    except Exception as e:
        return f"格式化专栏文章时出错: {e}"

# --- 主函数 ---
def main():
    """启动MCP服务器"""
    logger.info("BiliStalkerMCP Server is starting...")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
