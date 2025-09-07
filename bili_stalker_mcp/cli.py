import os
import logging
import json
from typing import Any, Dict, Optional

from fastmcp import FastMCP
from mcp.types import TextContent
from bilibili_api.exceptions import ApiException

from .core import (
    get_credential,
    get_user_id_by_username,
    fetch_user_info,
    fetch_user_videos,
    fetch_user_dynamics,
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
def _resolve_user_id(user_id: Optional[int], username: Optional[str]) -> Optional[int]:
    """根据user_id或username解析最终的用户ID"""
    if user_id:
        return user_id
    return get_user_id_by_username(username)

# --- MCP工具定义 ---
@mcp.tool()
def get_user_video_updates(user_id: int = None, username: str = None, limit: int = 10) -> Dict[str, Any]:
    """
    获取B站用户的视频列表，支持用户名或用户ID查询。

    使用用户名时会自动搜索并匹配最相关的用户。
    返回完整的视频详情，包括播放量、时长、发布日期等。
    
    **提示**: 结果可用 `format_video_response` 提示进行格式化。
    """
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
        video_data = fetch_user_videos(target_uid, limit, cred)

        return {"user": user_info, **video_data}
    except ApiException as e:
        logger.error(f"Bilibili API Error in get_user_video_updates: {e}")
        return {"error": f"Bilibili API Error: {e.msg} (Code: {e.code})"}
    except Exception as e:
        logger.error(f"An unexpected error in get_user_video_updates: {e}")
        return {"error": f"An unexpected error occurred: {e}"}

@mcp.tool()
def get_user_dynamic_updates(user_id: int = None, username: str = None, limit: int = 10, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """
    获取B站用户的动态列表，支持类型过滤和时间轴展示。

    支持多种动态类型过滤，显示完整的互动统计和媒体内容。
    包含文本、图片、视频和文章等多种动态形式。

    **提示**: 结果可用 `format_dynamic_response` 提示进行格式化。
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
        target_uid = _resolve_user_id(user_id, username)
        if not target_uid:
            return {"error": f"User '{username or user_id}' not found. Please check the username or user ID."}

        user_info = fetch_user_info(target_uid, cred)
        if "error" in user_info:
            return {"error": f"Failed to fetch user info: {user_info['error']}"}

        dynamic_data = fetch_user_dynamics(target_uid, limit, cred, dynamic_type)
        if "error" in dynamic_data:
            return {"error": f"Failed to fetch dynamics: {dynamic_data['error']}"}

        return {"user": user_info, **dynamic_data}
    except ApiException as e:
        logger.error(f"Bilibili API Error in get_user_dynamic_updates: {e}")
        return {
            "error": "Bilibili API authentication rate-limited. Please check your credentials and try again later.",
            "code": e.code,
            "message": e.msg
        }
    except TimeoutError:
        logger.error("Request timeout in get_user_dynamic_updates")
        return {"error": "Request timed out. The Bilibili API may be experiencing high traffic."}
    except ConnectionError:
        logger.error("Connection error in get_user_dynamic_updates")
        return {"error": "Connection failed. Please check your internet connection."}
    except Exception as e:
        logger.error(f"An unexpected error in get_user_dynamic_updates: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}. Please try again or contact support."}

# --- MCP资源定义 ---
@mcp.resource(SCHEMAS_URI)
def get_data_schemas() -> TextContent:
    """获取数据结构schema，提供工具返回数据的标准格式定义"""
    schemas = {
        "video_schema": {
            "type": "object",
            "properties": {
                "bvid": {"type": "string", "description": "视频唯一标识"},
                "title": {"type": "string", "description": "视频标题"},
                "play": {"type": "integer", "description": "播放次数"},
                "url": {"type": "string", "description": "视频完整URL"}
            },
        },
        "dynamic_schema": {
            "type": "object",
            "properties": {
                "dynamic_id": {"type": "string", "description": "动态唯一标识"},
                "type": {"type": "string", "description": "动态类型"},
                "content": {"type": "object", "description": "动态内容"},
            },
        }
    }
    return TextContent(type="text", text=json.dumps(schemas), mimeType="application/json")


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
            md += f"| [{v['title']}]({v['url']}) | {v['play']} | {v['length']} | {v['created']} |\n"
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
            md += f"- **[{d['type']}]** {d['timestamp']}\n"
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
