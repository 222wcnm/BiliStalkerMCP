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
    _detect_network_environment,
)
from .config import (
    SCHEMAS_URI,
    DynamicType,
    DEFAULT_HEADERS,
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
def _resolve_user_id(user_id: Optional[int], username: Optional[str]) -> Optional[int]:
    """根据user_id或username解析最终的用户ID"""
    if user_id:
        return user_id
    return get_user_id_by_username(username)

# --- MCP工具定义 ---
@mcp.tool()
def get_user_video_updates(user_id: int = None, username: str = None, limit: int = 10) -> Dict[str, Any]:
    """
    获取指定B站用户的最新视频列表。

    Args:
        user_id (int, optional): 用户的数字ID。
        username (str, optional): 用户的昵称。如果提供了`username`，将自动搜索并使用最匹配的用户ID。`user_id` 和 `username` 必须提供一个。
        limit (int, optional): 返回视频的数量，默认为10，范围在1到50之间。

    Returns:
        Dict[str, Any]: 包含用户信息和视频列表的字典。
                         - `user`: 包含用户`mid`, `name`, `face`等信息的字典。
                         - `videos`: 视频对象列表。
                         - `error`: 如果发生错误，则包含错误信息。
    """
    # 检测网络环境
    env_info = _detect_network_environment()
    if env_info["is_cloud_env"]:
        logger.info("检测到云环境，启用网络优化配置")
    
    if not cred:
        return {"error": "Credential is not configured."}
    if not user_id and not username:
        return {"error": "Either user_id or username must be provided."}
    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}

    try:
        target_uid = _resolve_user_id(user_id, username)
        if not target_uid:
            return {"error": "User not found."}

        user_info = fetch_user_info(target_uid, cred)
        if "error" in user_info:
            return {"user": user_info, "error": user_info["error"]}

        video_data = fetch_user_videos(target_uid, limit, cred)
        if "error" in video_data:
            return {"user": user_info, **video_data}

        return {"user": user_info, **video_data}
    except Exception as e:
        logger.error(f"An unexpected error in get_user_video_updates: {e}")
        return {"error": f"An unexpected error occurred: {e}"}

@mcp.tool()
def get_user_dynamic_updates(user_id: int = None, username: str = None, limit: int = 10, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """
    获取指定B站用户的最新动态列表。

    Args:
        user_id (int, optional): 用户的数字ID。
        username (str, optional): 用户的昵称。如果提供了`username`，将自动搜索并使用最匹配的用户ID。`user_id` 和 `username` 必须提供一个。
        limit (int, optional): 返回动态的数量，默认为10，范围在1到50之间。
        dynamic_type (str, optional): 动态类型过滤，可以是 "ALL", "VIDEO", "ARTICLE", "DRAW"。默认为 "ALL"。

    Returns:
        Dict[str, Any]: 包含用户信息和动态列表的字典。
                         - `user`: 包含用户`mid`, `name`, `face`等信息的字典。
                         - `dynamics`: 动态对象列表，每个动态都包含格式化好的 `publish_time` (ISO 8601 格式)。
                         - `error`: 如果发生错误，则包含错误信息。
    """
    # 检测网络环境
    env_info = _detect_network_environment()
    if env_info["is_cloud_env"]:
        logger.info("检测到云环境，启用网络优化配置")
    
    if not cred:
        return {"error": "Credential is not configured. Please set SESSDATA, BILI_JCT, and BUVID3 environment variables."}
    if not user_id and not username:
        return {"error": "Either user_id or username must be provided."}
    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}
    if dynamic_type not in DynamicType.VALID_TYPES:
        return {"error": f"Invalid dynamic_type. Must be one of {DynamicType.VALID_TYPES}"}

    try:
        target_uid = _resolve_user_id(user_id, username)
        if not target_uid:
            return {"error": f"User '{username or user_id}' not found. Please check the username or user ID."}

        user_info = fetch_user_info(target_uid, cred)
        if "error" in user_info:
            return {"user": user_info, "error": user_info["error"]}

        dynamic_data = fetch_user_dynamics(target_uid, limit, cred, dynamic_type)
        if "error" in dynamic_data:
            return {"user": user_info, **dynamic_data}

        return {"user": user_info, **dynamic_data}
    except Exception as e:
        logger.error(f"An unexpected error in get_user_dynamic_updates: {e}")
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
                    # 解析ISO 8601格式的日期字符串
                    dt_object = datetime.strptime(v['created'], '%Y-%m-%dT%H:%M:%SZ')
                    publish_date = dt_object.strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    publish_date = v['created'] # 如果解析失败，则显示原始值
            
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

# --- 主函数 ---
def main():
    """启动MCP服务器"""
    logger.info("BiliStalkerMCP Server is starting...")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
