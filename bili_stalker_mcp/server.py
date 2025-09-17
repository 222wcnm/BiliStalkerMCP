"""
BiliStalkerMCP 服务器

此模块定义 FastMCP 服务器，包含工具、资源和提示的完整定义。
按照 FastMCP 官方文档的最佳实践进行组织。
"""

import os
import logging
import json
from typing import Any, Dict, Optional, Callable, Coroutine, Union, Annotated
from datetime import datetime, timezone
from functools import wraps

from fastmcp import FastMCP
from mcp.types import TextContent
from pydantic import Field
from bilibili_api.exceptions import ApiException

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
def _format_timestamp(timestamp: Optional[int]) -> str:
    """
    统一的时间戳格式化函数，处理B站API返回的时间戳
    
    Args:
        timestamp: Unix时间戳（秒），可能为None
        
    Returns:
        格式化的时间字符串，如果timestamp无效则返回"未知时间"
    """
    if timestamp is None:
        return "未知时间"
    
    try:
        # B站API返回的时间戳通常是UTC时间戳
        # 转换为本地时间显示
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError, OSError) as e:
        logger.warning(f"时间戳转换失败: {timestamp}, 错误: {e}")
        return f"时间戳错误({timestamp})"

async def _resolve_user_id(user_id: Union[int, None], username: Union[str, None]) -> Union[int, None]:
    """根据user_id或username解析最终的用户ID"""
    if user_id is not None:
        return user_id
    if username:
        return await get_user_id_by_username(username)
    return None

# --- 用于预检的装饰器 ---
def precheck(func: Callable[..., Coroutine[Any, Any, Dict[str, Any]]]) -> Callable[..., Coroutine[Any, Any, Dict[str, Any]]]:
    """
    处理凭证和用户ID解析的模板代码的装饰器。
    """
    @wraps(func)
    async def wrapper(user_id: Union[int, None] = None, username: Union[str, None] = None, **kwargs: Any) -> Dict[str, Any]:
        if not cred:
            return {"error": "凭证未配置。请设置 SESSDATA、BILI_JCT 和 BUVID3 环境变量。"}
        if user_id is None and not username:
            return {"error": "必须提供 user_id 或 username 中的一个。"}

        try:
            target_uid = await _resolve_user_id(user_id, username)
            if not target_uid:
                if username:
                    return {"error": f"用户 '{username}' 未找到。请检查用户名拼写或稍后重试。"}
                else:
                    return {"error": f"用户 ID {user_id} 无效或不存在。请检查用户 ID 是否正确。"}
            
            # 将解析后的UID传递给被装饰的函数，确保类型正确
            return await func(user_id=target_uid, **kwargs)
        except Exception as e:
            logger.error(f"An unexpected error in decorator for {func.__name__}: {e}")
            return {"error": f"预检查过程中发生未知错误: {str(e)}。"}
            
    return wrapper

# --- MCP工具定义 ---
@mcp.tool()
@precheck
async def get_user_info(
    user_id: Annotated[Optional[int], Field(description="用户的Bilibili UID")] = None, 
    username: Annotated[Optional[str], Field(description="用户的Bilibili昵称")] = None
) -> Dict[str, Any]:
    """
    获取Bilibili用户的个人主页信息。

    支持使用用户名或UID，两者效力相同。返回用户详细资料：昵称、签名、等级、粉丝数、关注数等。
    
    您必须提供 user_id 或 username 中的一个。

    :param user_id: 用户的Bilibili UID (可选)。
    :param username: 用户的Bilibili昵称 (可选)。
    :return: 包含用户详细信息的JSON对象。
    """
    # @precheck装饰器已经检查了cred，所以这里安全
    assert cred is not None
    # @precheck装饰器确保user_id不为None
    assert user_id is not None
    return await fetch_user_info(user_id, cred)


@mcp.tool()
@precheck
async def get_user_video_updates(
    user_id: Annotated[Optional[int], Field(description="用户的Bilibili UID")] = None, 
    username: Annotated[Optional[str], Field(description="用户的Bilibili昵称")] = None, 
    page: Annotated[int, Field(description="页码，默认为1", ge=1)] = 1, 
    limit: Annotated[int, Field(description="每页数量，默认为10，最大为50", ge=1, le=50)] = 10
) -> Dict[str, Any]:
    """
    获取Bilibili用户最近发布的视频列表。

    支持使用用户名或UID，两者效力相同。返回视频详细信息：标题、描述、播放量、弹幕数、封面图、字幕信息等。
    字幕信息包含：是否有字幕、字幕数量、字幕语言列表和字幕下载URL。
    
    您必须提供 user_id 或 username 中的一个。

    :param user_id: 用户的Bilibili UID (可选)。
    :param username: 用户的Bilibili昵称 (可选)。
    :param page: 页码，默认为1。
    :param limit: 每页数量，默认为10，最大为50。
    :return: 包含视频列表的JSON对象，每个视频包含详细的字幕信息。
    """
    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}
    # @precheck装饰器已经检查了cred，所以这里安全
    assert cred is not None
    # @precheck装饰器确保user_id不为None
    assert user_id is not None
    return await fetch_user_videos(user_id, page, limit, cred)

@mcp.tool()
@precheck
async def get_user_dynamic_updates(
    user_id: Annotated[Optional[int], Field(description="用户的Bilibili UID")] = None, 
    username: Annotated[Optional[str], Field(description="用户的Bilibili昵称")] = None, 
    offset: Annotated[int, Field(description="动态偏移量，用于分页，默认为0", ge=0)] = 0, 
    limit: Annotated[int, Field(description="需要获取的动态数量，默认为10，最大为50", ge=1, le=50)] = 10, 
    dynamic_type: Annotated[str, Field(description="动态类型，可以是 'ALL', 'VIDEO', 'ARTICLE', 'ANIME', 'DRAW'")] = "ALL"
) -> Dict[str, Any]:
    """
    获取Bilibili用户最近发布的动态。

    支持使用用户名或UID，两者效力相同。可指定动态类型（视频、专栏、图文等）和获取数量。
    返回动态详细信息：类型、发布时间、文本内容、点赞/评论/转发数。
    
    您必须提供 user_id 或 username 中的一个。

    :param user_id: 用户的Bilibili UID (可选)。
    :param username: 用户的Bilibili昵称 (可选)。
    :param offset: 动态偏移量, 用于分页，默认为0。
    :param limit: 需要获取的动态数量，默认为10，最大为50。
    :param dynamic_type: 动态类型，可以是 "ALL", "VIDEO", "ARTICLE", "ANIME", "DRAW"。默认为 "ALL"。
    :return: 包含动态列表的JSON对象。
    """
    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}
    if dynamic_type not in DynamicType.VALID_TYPES:
        return {"error": f"Invalid dynamic_type. Must be one of {DynamicType.VALID_TYPES}"}
    # @precheck装饰器已经检查了cred，所以这里安全
    assert cred is not None
    # @precheck装饰器确保user_id不为None
    assert user_id is not None
    return await fetch_user_dynamics(user_id, offset, limit, cred, dynamic_type)


@mcp.tool()
@precheck
async def get_user_articles(
    user_id: Annotated[Optional[int], Field(description="用户的Bilibili UID")] = None, 
    username: Annotated[Optional[str], Field(description="用户的Bilibili昵称")] = None, 
    page: Annotated[int, Field(description="页码，默认为1", ge=1)] = 1, 
    limit: Annotated[int, Field(description="每页数量，默认为10，最大为50", ge=1, le=50)] = 10
) -> Dict[str, Any]:
    """
    获取Bilibili用户最近发布的专栏文章列表。

    支持使用用户名或UID，两者效力相同。返回文章详细信息：标题、摘要、阅读量、封面图URL等。
    
    您必须提供 user_id 或 username 中的一个。

    :param user_id: 用户的Bilibili UID (可选)。
    :param username: 用户的Bilibili昵称 (可选)。
    :param page: 页码，默认为1。
    :param limit: 每页数量，默认为10，最大为50。
    :return: 包含文章列表的JSON对象。
    """
    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}
    # @precheck装饰器已经检查了cred，所以这里安全
    assert cred is not None
    # @precheck装饰器确保user_id不为None
    assert user_id is not None
    return await fetch_user_articles(user_id, page, limit, cred)

@mcp.tool()
@precheck
async def get_user_followings(
    user_id: Annotated[Optional[int], Field(description="用户的Bilibili UID")] = None, 
    username: Annotated[Optional[str], Field(description="用户的Bilibili昵称")] = None, 
    page: Annotated[int, Field(description="页码，默认为1", ge=1)] = 1, 
    limit: Annotated[int, Field(description="每页数量，默认为20，最大为50", ge=1, le=50)] = 20
) -> Dict[str, Any]:
    """
    获取Bilibili用户的关注列表。

    支持使用用户名或UID，两者效力相同。返回关注用户详细信息：昵称、签名、头像等。
    
    您必须提供 user_id 或 username 中的一个。

    :param user_id: 用户的Bilibili UID (可选)。
    :param username: 用户的Bilibili昵称 (可选)。
    :param page: 页码，默认为1。
    :param limit: 每页数量，默认为20，最大为50。
    :return: 包含关注用户列表的JSON对象。
    """
    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}
    # @precheck装饰器已经检查了cred，所以这里安全
    assert cred is not None
    # @precheck装饰器确保user_id不为None
    assert user_id is not None
    return await fetch_user_followings(user_id, page, limit, cred)

# --- 资源定义（按照 FastMCP 最佳实践添加） ---
@mcp.resource("bili://user/{user_id}/info")
async def get_user_info_resource(user_id: int) -> str:
    """获取用户信息资源"""
    if not cred:
        return json.dumps({"error": "Credential not configured"}, ensure_ascii=False)
    
    try:
        user_info = await fetch_user_info(user_id, cred)
        return json.dumps(user_info, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@mcp.resource("bili://user/{user_id}/videos")
async def get_user_videos_resource(user_id: int) -> str:
    """获取用户视频资源"""
    if not cred:
        return json.dumps({"error": "Credential not configured"}, ensure_ascii=False)
    
    try:
        videos = await fetch_user_videos(user_id, 1, 10, cred)
        return json.dumps(videos, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@mcp.resource("bili://user/{user_id}/dynamics")
async def get_user_dynamics_resource(user_id: int) -> str:
    """获取用户动态资源"""
    if not cred:
        return json.dumps({"error": "Credential not configured"}, ensure_ascii=False)
    
    try:
        dynamics = await fetch_user_dynamics(user_id, 0, 10, cred)
        return json.dumps(dynamics, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

# --- 提示预设 (用于规范模型输出格式) ---
@mcp.prompt()
def format_user_info_response(user_info_json: str) -> str:
    """格式化用户个人信息为Markdown, 支持get_user_info工具的输出"""
    try:
        data = json.loads(user_info_json)
        if not data or data.get("error"):
            return f"获取用户信息失败: {data.get('error', '未知错误')}"

        md = f"### {data.get('name', 'N/A')}\n\n"
        if data.get('face'):
            md += f"![头像]({data.get('face')})\n\n"
        
        if data.get('sign'):
            md += f"> {data.get('sign')}\n\n"

        md += f"- **等级**: LV.{data.get('level', 'N/A')}\n"
        md += f"- **关注数**: {data.get('following', 'N/A')}\n"
        md += f"- **粉丝数**: {data.get('follower', 'N/A')}\n"
        md += f"- **性别**: {data.get('sex', 'N/A')}\n"
        if data.get('birthday'):
            md += f"- **生日**: {data.get('birthday')}\n"
        
        live_room = data.get('live_room')
        if live_room and live_room.get('liveStatus') == 1:
            md += "\n---\n\n"
            md += "#### 直播间信息\n"
            md += f"- **标题**: {live_room.get('title', 'N/A')}\n"
            md += "- **状态**: 正在直播\n"
            if live_room.get('url'):
                md += f"- **链接**: [点击进入]({live_room.get('url')})\n"
        
        return md
    except Exception as e:
        return f"格式化用户信息时出错: {e}"

@mcp.prompt()
def format_video_response(videos_json: str) -> str:
    """格式化视频数据为Markdown, 支持get_user_video_updates工具的输出，现在包含字幕信息"""
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
            
            # 基本信息
            md += f"- **播放**: {v.get('play', 0)} | **点赞**: {v.get('like', 0)} | **发布于**: {_format_timestamp(v.get('created'))}\n"
            
            # 字幕信息
            subtitle = v.get('subtitle', {})
            if subtitle.get('has_subtitle'):
                subtitle_count = subtitle.get('subtitle_count', 0)
                subtitle_langs = []
                for sub in subtitle.get('subtitle_list', []):
                    lang_doc = sub.get('lan_doc', sub.get('lan', '未知语言'))
                    subtitle_langs.append(lang_doc)
                
                md += f"- **字幕**: 有 ({subtitle_count}种语言: {', '.join(subtitle_langs)})\n"
            else:
                md += f"- **字幕**: 无\n"
            
            md += "\n"
        
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
            md += f"**类型**: {d.get('type')} | **发布于**: {_format_timestamp(d.get('timestamp'))}\n"
            md += f"> {d.get('text_content', '')}\n\n"
            if d.get('images'):
                md += " ".join([f"![image]({img})" for img in d['images']]) + "\n\n"
            md += "---\n"
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
            md += f"- **阅读**: {a.get('stats', {}).get('view', 0)} | **发布于**: {_format_timestamp(a.get('publish_time'))}\n"
            md += f"> {a.get('summary', '无摘要')}\n\n"
        return md
    except Exception as e:
        return f"格式化专栏文章时出错: {e}"

@mcp.prompt()
def format_followings_response(followings_json: str) -> str:
    """格式化关注列表数据为Markdown, 支持get_user_followings工具的输出"""
    try:
        data = json.loads(followings_json)
        followings_list = data.get("followings", [])
        if not followings_list:
            return "用户没有关注任何人。"

        md = "### 关注列表\n\n"
        for f in followings_list:
            md += f"#### {f.get('uname', '无昵称')}\n"
            if f.get('face'):
                md += f"![avatar]({f['face']})\n\n"
            if f.get('sign'):
                md += f"> {f.get('sign')}\n\n"
            md += f"- **UID**: {f.get('mid')}\n"
            if f.get('official_verify'):
                md += f"- **认证**: {f.get('official_verify')}\n"
            md += "---\n"
        return md
    except Exception as e:
        return f"格式化关注列表数据时出错: {e}"

def run():
    """运行MCP服务器"""
    logger.info("BiliStalkerMCP Server is starting...")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    run()