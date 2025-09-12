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
    """
    获取指定B站用户的个人信息。

    Args:
        user_id (int, optional): 用户的数字ID。
        username (str, optional): 用户的昵称。如果提供了`username`，将自动搜索并使用最匹配的用户ID。`user_id` 和 `username` 必须提供一个。

    Returns:
        Dict[str, Any]: 包含用户详细信息的字典。
    """
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
    """
    获取指定B站用户的最新视频列表。

    Args:
        user_id (int, optional): 用户的数字ID。
        username (str, optional): 用户的昵称。如果提供了`username`，将自动搜索并使用最匹配的用户ID。`user_id` 和 `username` 必须提供一个。
        limit (int, optional): 返回视频的数量，默认为10，范围在1到50之间。

    Returns:
        Dict[str, Any]: 包含视频列表的字典。
    """
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
    """
    获取指定B站用户的最新动态列表。

    Args:
        user_id (int, optional): 用户的数字ID。
        username (str, optional): 用户的昵称。如果提供了`username`，将自动搜索并使用最匹配的用户ID。`user_id` 和 `username` 必须提供一个。
        limit (int, optional): 返回动态的数量，默认为10，范围在1到50之间。
        dynamic_type (str, optional): 动态类型过滤，可以是 "ALL", "VIDEO", "ARTICLE", "DRAW"。默认为 "ALL"。

    Returns:
        Dict[str, Any]: 包含动态列表的字典。
    """
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
    """
    获取指定B站用户的最新专栏文章列表。

    Args:
        user_id (int, optional): 用户的数字ID。
        username (str, optional): 用户的昵称。如果提供了`username`，将自动搜索并使用最匹配的用户ID。`user_id` 和 `username` 必须提供一个。
        limit (int, optional): 返回文章的数量，默认为10，范围在1到50之间。

    Returns:
        Dict[str, Any]: 包含文章列表的字典。
    """
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
def format_video_response(videos: str) -> str:
    """格式化视频数据为Markdown表格，支持get_user_video_updates工具的输出"""
    try:
        data = json.loads(videos)
        user_info = data.get("user", {})
        video_list = data.get("videos", [])

        if not video_list:
            return f"**{user_info.get('name', '用户')}** 最近没有发布新视频。"

        md = f"### {user_info.get('name', '用户')} 的最新视频\n\n"
        md += "| 标题 | 播放量 | 时长 | 发布日期 |\n"
        md += "| --- | --- | --- | --- |\n"
        for v in video_list:
            publish_date = "N/A"
            if v.get('created'):
                try:
                    dt_object = datetime.fromisoformat(v['created'].replace('Z', '+00:00'))
                    publish_date = dt_object.strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    publish_date = v['created']
            
            md += f"| [{v['title']}]({v['url']}) | {v['play']} | {v['length']} | {publish_date} |\n"
        return md
    except Exception as e:
        return f"格式化视频数据时出错: {e}"


@mcp.prompt()
def format_dynamic_response(dynamics: str) -> str:
    """格式化动态数据为按时间倒序的Markdown列表，支持get_user_dynamic_updates工具的输出"""
    try:
        data = json.loads(dynamics)
        user_info = data.get("user", {})
        dynamic_list = data.get("dynamics", [])

        if not dynamic_list:
            return f"**{user_info.get('name', '用户')}** 最近没有发布新动态。"

        md = f"### {user_info.get('name', '用户')} 的最新动态\n\n"
        for d in dynamic_list:
            md += f"- **[{d['type']}]** {d.get('publish_time', d.get('timestamp'))}\n"
            md += f"  > {d['content']['text']}\n"
            if d.get('url'):
                md += f"  > [查看详情]({d['url']})\n"
            md += "\n"
        return md
    except Exception as e:
        return f"格式化动态数据时出错: {e}"

@mcp.prompt()
def format_articles_response(articles: str) -> str:
    """格式化专栏文章数据为Markdown列表，支持get_user_articles工具的输出"""
    try:
        data = json.loads(articles)
        article_list = data.get("articles", [])

        if not article_list:
            return "最近没有发布新专栏文章。"

        md = "### 最新专栏文章\n\n"
        for article in article_list:
            publish_date = "N/A"
            if article.get('publish_time'):
                try:
                    dt_object = datetime.fromisoformat(article['publish_time'].replace('Z', '+00:00'))
                    publish_date = dt_object.strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    publish_date = article['publish_time']
            
            md += f"- **[{publish_date}]** [{article['title']}]({article['url']})\n"
            if article.get('summary'):
                md += f"  > {article['summary']}\n"
            md += "\n"
        return md
    except Exception as e:
        return f"格式化专栏文章数据时出错: {e}"

# --- 主函数 ---
def main():
    """启动MCP服务器"""
    logger.info("BiliStalkerMCP Server is starting...")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()