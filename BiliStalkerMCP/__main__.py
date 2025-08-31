import os
import time
import logging
import json
from typing import Any, Dict, List, Optional, Union
from bilibili_api import user, sync, Credential, search
from bilibili_api.exceptions import ApiException
from fastmcp import FastMCP
from mcp.types import TextContent
import requests

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 从环境变量中获取SESSDATA
SESSDATA = os.environ.get("SESSDATA", "")
BILI_JCT = os.environ.get("BILI_JCT", "")
BUVID3 = os.environ.get("BUVID3", "")

# 创建凭证对象
cred = Credential(
    sessdata=SESSDATA,
    bili_jct=BILI_JCT,
    buvid3=BUVID3
)

# B站动态API配置
BILIBILI_DYNAMIC_API_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
REQUEST_DELAY = 0.1  # 请求间隔时间（秒）

mcp = FastMCP("BiliStalkerMCP")

# 资源URI模板
USER_INFO_URI_TEMPLATE = "bili://user/{user_id}/info"
USER_VIDEOS_URI_TEMPLATE = "bili://user/{user_id}/videos"
USER_DYNAMICS_URI_TEMPLATE = "bili://user/{user_id}/dynamics"

def fetch_dynamic_data(offset: str, host_mid: str) -> Optional[Dict[str, Any]]:
    """
    从B站API获取动态数据
    
    Args:
        offset: 分页偏移量
        host_mid: B站用户mid
        
    Returns:
        API响应数据，失败时返回None
    """
    try:
        # 添加请求延时，避免频繁请求
        time.sleep(REQUEST_DELAY)

        # 构建请求头
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            'Cookie': f"buvid3={BUVID3}; SESSDATA={SESSDATA}; bili_jct={BILI_JCT}"
        }

        # 构建请求参数
        params = {
            "offset": offset,
            "host_mid": host_mid
        }

        # 发送HTTP请求
        response = requests.get(
            BILIBILI_DYNAMIC_API_URL, 
            params=params, 
            headers=headers,
            timeout=10
        )
        
        # 检查HTTP状态码
        response.raise_for_status()

        # 解析JSON响应
        data = response.json()
        
        # 检查API响应状态
        if data.get("code") != 0:
            logger.warning(f"API返回错误: {data.get('message', '未知错误')}")
            return None
        
        return data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"网络请求失败: {str(e)}")
        return None
    except ValueError as e:
        logger.error(f"JSON解析失败: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"获取数据时发生未知错误: {str(e)}")
        return None

def parse_dynamic_data(data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    解析B站动态数据，提取动态内容和下一页偏移量
    
    Args:
        data: API响应数据
        
    Returns:
        tuple: (动态内容列表, 下一页偏移量)
    """
    dynamics = []
    
    if not isinstance(data, dict) or data.get("code") != 0:
        logger.warning("数据格式错误或API返回失败")
        return dynamics, None

    try:
        items = data.get("data", {}).get("items", [])
        
        for item in items:
            try:
                modules = item.get("modules", {})
                module_dynamic = modules.get("module_dynamic", {})
                module_author = modules.get("module_author", {})
                
                # 提取动态基本信息
                dynamic_id = item.get("id_str")
                timestamp = item.get("modules", {}).get("module_author", {}).get("pub_ts")
                type_name = item.get("type")
                
                # 提取文本内容
                text_content = ""
                desc = module_dynamic.get("desc", {})
                if desc and desc.get("text"):
                    text_content = desc.get("text")
                
                # 提取图片
                pictures = []
                major = module_dynamic.get("major", {})
                if major and major.get("draw", {}).get("items"):
                    pictures = [img.get("src", "") for img in major.get("draw", {}).get("items", [])]
                
                # 提取视频信息
                video_info = None
                if major and major.get("archive"):
                    archive = major.get("archive", {})
                    video_info = {
                        "bvid": archive.get("bvid"),
                        "title": archive.get("title"),
                        "cover": archive.get("cover"),
                        "duration": archive.get("duration_text"),
                        "url": f"https://www.bilibili.com/video/{archive.get('bvid')}" if archive.get('bvid') else None
                    }
                
                # 提取文章信息
                article_info = None
                if major and major.get("article"):
                    article = major.get("article", {})
                    article_info = {
                        "id": article.get("id"),
                        "title": article.get("title"),
                        "summary": article.get("desc"),
                        "banner_url": article.get("banner_url"),
                        "url": f"https://www.bilibili.com/read/{article.get('id')}" if article.get('id') else None
                    }
                
                # 统计信息
                stat = item.get("modules", {}).get("module_stat", {})
                
                dynamics.append({
                    "dynamic_id": dynamic_id,
                    "timestamp": timestamp,
                    "type": type_name,
                    "stat": {
                        "like": stat.get("like", {}).get("count", 0),
                        "comment": stat.get("comment", {}).get("count", 0),
                        "forward": stat.get("forward", {}).get("count", 0)
                    },
                    "content": {
                        "text": text_content,
                        "pictures": pictures,
                        "video": video_info,
                        "article": article_info
                    }
                })
                
            except (AttributeError, TypeError) as e:
                logger.debug(f"解析单条动态时出错: {str(e)}")
                continue

        # 检查是否还有更多数据
        data_info = data.get('data', {})
        has_more = data_info.get('has_more', False)
        next_offset = data_info.get('offset') if has_more else None
        
        logger.debug(f"本页解析到{len(dynamics)}条动态，{'有' if has_more else '无'}更多数据")
        return dynamics, next_offset
        
    except Exception as e:
        logger.error(f"解析动态数据时发生错误: {str(e)}")
        return dynamics, None


def get_user_info_resource(user_id: int) -> Dict[str, Any]:
    """
    获取用户信息资源
    
    Args:
        user_id: B站用户ID
        
    Returns:
        用户信息字典
    """
    try:
        if not SESSDATA:
            return {"error": "SESSDATA environment variable is not set."}
            
        # 创建用户对象
        u = user.User(uid=user_id, credential=cred)
        
        # 获取用户信息
        user_info = sync(u.get_user_info())
        
        return {
            "mid": user_info.get("mid"),
            "name": user_info.get("name"),
            "face": user_info.get("face"),
            "sign": user_info.get("sign"),
            "level": user_info.get("level"),
            "following": user_info.get("following"),
            "follower": user_info.get("follower")
        }
    except Exception as e:
        logger.error(f"获取用户信息资源时发生错误: {str(e)}")
        return {"error": f"Failed to get user info: {str(e)}"}


def get_user_videos_resource(user_id: int, limit: int = 10) -> Dict[str, Any]:
    """
    获取用户视频资源
    
    Args:
        user_id: B站用户ID
        limit: 视频数量限制
        
    Returns:
        视频列表字典
    """
    try:
        if not SESSDATA:
            return {"error": "SESSDATA environment variable is not set."}
            
        if not (1 <= limit <= 50):
            return {"error": "Limit must be between 1 and 50."}
            
        # 创建用户对象
        u = user.User(uid=user_id, credential=cred)
        
        # 获取用户信息
        user_info = sync(u.get_user_info())
        
        # 获取视频列表
        video_list = sync(u.get_videos(ps=limit))
        
        # 处理视频列表
        raw_videos = video_list.get("list", {}).get("vlist", [])
        processed_videos = []
        for video in raw_videos:
            processed_video = {
                "bvid": video.get("bvid"),
                "aid": video.get("aid"),
                "title": video.get("title"),
                "description": video.get("description"),
                "created": video.get("created"),
                "length": video.get("length"),
                "pic": video.get("pic"),
                "play": video.get("play"),
                "favorites": video.get("favorites"),
                "author": video.get("author"),
                "mid": video.get("mid"),
                "url": f"https://www.bilibili.com/video/{video.get('bvid')}" if video.get('bvid') else None
            }
            processed_videos.append(processed_video)

        return {
            "user": {
                "mid": user_info.get("mid"),
                "name": user_info.get("name"),
                "face": user_info.get("face")
            },
            "videos": processed_videos,
            "total": video_list.get("page", {}).get("count", 0)
        }
    except Exception as e:
        logger.error(f"获取用户视频资源时发生错误: {str(e)}")
        return {"error": f"Failed to get user videos: {str(e)}"}


def get_user_dynamics_resource(user_id: int, limit: int = 10, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """
    获取用户动态资源
    
    Args:
        user_id: B站用户ID
        limit: 动态数量限制
        dynamic_type: 动态类型
        
    Returns:
        动态列表字典
    """
    try:
        if not SESSDATA:
            return {"error": "SESSDATA environment variable is not set."}
            
        if not (1 <= limit <= 50):
            return {"error": "Limit must be between 1 and 50."}
            
        # 验证动态类型
        valid_types = ["ALL", "VIDEO", "ARTICLE", "ANIME"]
        if dynamic_type not in valid_types:
            return {"error": f"Dynamic type must be one of: {', '.join(valid_types)}"}

        # 创建用户对象
        u = user.User(uid=user_id, credential=cred)
        
        # 获取用户信息
        user_info = sync(u.get_user_info())
        
        # 使用新的HTTP API方式获取动态
        dynamics = []
        offset = ""
        collected_count = 0
        
        # 循环获取动态直到达到限制数量或没有更多数据
        while collected_count < limit:
            # 获取一页动态数据
            data = fetch_dynamic_data(offset, str(user_id))
            if not data:
                break
                
            # 解析动态数据
            page_dynamics, next_offset = parse_dynamic_data(data)
            if not page_dynamics:
                break
                
            # 添加到结果中
            for dyn in page_dynamics:
                if collected_count >= limit:
                    break
                dynamics.append(dyn)
                collected_count += 1
                
            # 检查是否还有更多数据
            if not next_offset:
                break
                
            offset = next_offset

        return {
            "user": {
                "mid": user_info.get("mid"),
                "name": user_info.get("name"),
                "face": user_info.get("face")
            },
            "dynamics": dynamics,
            "count": len(dynamics)
        }
    except Exception as e:
        logger.error(f"获取用户动态资源时发生错误: {str(e)}")
        return {"error": f"Failed to get user dynamics: {str(e)}"}


def parse_resource_uri(uri: str) -> tuple[str, dict]:
    """
    解析资源URI，提取资源类型和参数
    
    Args:
        uri: 资源URI
        
    Returns:
        tuple: (资源类型, 参数字典)
    """
    try:
        # 解析URI
        if uri.startswith("bili://user/"):
            # 移除前缀
            path = uri[12:]  # 移除 "bili://user/"
            
            # 分割路径
            parts = path.split("/")
            if len(parts) < 2:
                return "unknown", {}
                
            user_id_str = parts[0]
            resource_type = parts[1]
            
            # 解析用户ID
            try:
                user_id = int(user_id_str)
            except ValueError:
                return "unknown", {}
            
            # 解析查询参数
            params = {}
            if "?" in resource_type:
                resource_type, query_string = resource_type.split("?", 1)
                for param in query_string.split("&"):
                    if "=" in param:
                        key, value = param.split("=", 1)
                        params[key] = value
            
            return resource_type, {
                "user_id": user_id,
                "limit": int(params.get("limit", 10)),
                "type": params.get("type", "ALL")
            }
            
        return "unknown", {}
    except Exception as e:
        logger.error(f"解析资源URI时发生错误: {str(e)}")
        return "unknown", {}


def get_user_id(user_id: int = None, username: str = None) -> Optional[int]:
    """
    获取用户ID，支持通过user_id或username获取
    
    Args:
        user_id: B站用户ID
        username: B站用户名
        
    Returns:
        用户ID，失败时返回None
    """
    if user_id:
        return user_id
        
    if not username:
        logger.warning("必须提供user_id或username")
        return None

    try:
        # 通过搜索获取 UID（使用按类型搜索，用户类型）
        search_result = sync(search.search_by_type(
            keyword=username,
            search_type=search.SearchObjectType.USER,
            order_type=search.OrderUser.FANS
        ))
        # 兼容不同版本返回结构，提取用户列表
        result_list = None
        if isinstance(search_result, dict):
            if 'result' in search_result and isinstance(search_result['result'], list):
                result_list = search_result['result']
            elif 'data' in search_result and isinstance(search_result['data'], dict) and isinstance(search_result['data'].get('result'), list):
                result_list = search_result['data']['result']
        if not result_list:
            logger.warning(f"用户 '{username}' 未找到")
            return None
        
        # 筛选出完全匹配的用户
        exact_match = [u for u in result_list if u.get('uname') == username]
        if len(exact_match) == 1:
            return exact_match[0]['mid']
        elif len(exact_match) > 1:
            logger.warning(f"找到多个用户名完全匹配的用户 '{username}'，请使用user_id")
            return None
        else:
            # 如果没有精确匹配，返回第一个结果
            logger.warning(f"未找到用户名完全匹配的用户 '{username}'，使用最相关的用户")
            return result_list[0]['mid'] if result_list else None
            
    except Exception as e:
        logger.error(f"搜索用户时发生错误: {str(e)}")
        return None

@mcp.tool()
def get_user_video_updates(user_id: int = None, username: str = None, limit: int = 10) -> Dict[str, Any]:
    """
    获取B站用户的视频列表，支持用户名或用户ID查询。

    使用用户名时会自动搜索并匹配最相关的用户。
    返回完整的视频详情，包括播放量、时长、发布日期等。
    """
    if not SESSDATA:
        return {"error": "SESSDATA environment variable is not set."}
        
    if not user_id and not username:
        return {"error": "Either user_id or username must be provided."}

    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}

    try:
        # 使用统一的用户ID获取函数
        target_uid = get_user_id(user_id, username)
        if not target_uid:
            return {"error": "Failed to determine user_id."}

        # 创建用户对象
        u = user.User(uid=target_uid, credential=cred)
        
        # 获取用户信息
        user_info = sync(u.get_user_info())
        
        # 获取视频列表
        video_list = sync(u.get_videos(ps=limit))
        
        # 处理视频列表，确保包含 bvid 和 url
        raw_videos = video_list.get("list", {}).get("vlist", [])
        processed_videos = []
        for video in raw_videos:
            processed_video = {
                "bvid": video.get("bvid"),
                "aid": video.get("aid"),
                "title": video.get("title"),
                "description": video.get("description"),
                "created": video.get("created"),
                "length": video.get("length"),
                "pic": video.get("pic"),
                "play": video.get("play"),
                "favorites": video.get("favorites"),
                "author": video.get("author"),
                "mid": video.get("mid"),
                # 构造完整 URL
                "url": f"https://www.bilibili.com/video/{video.get('bvid')}" if video.get('bvid') else None
            }
            processed_videos.append(processed_video)

        return {
            "user": {
                "mid": user_info.get("mid"),
                "name": user_info.get("name"),
                "face": user_info.get("face"),
                "sign": user_info.get("sign"),
                "level": user_info.get("level"),
            },
            "videos": processed_videos,
            "total": video_list.get("page", {}).get("count", 0)
        }
    except ApiException as e:
        return {"error": f"Bilibili API Error: {e.msg}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
def get_user_dynamic_updates(user_id: int = None, username: str = None, limit: int = 10, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """
    获取B站用户的动态列表，支持类型过滤和时间轴展示。

    支持多种动态类型过滤，显示完整的互动统计和媒体内容。
    包含文本、图片、视频和文章等多种动态形式。
    """
    if not SESSDATA:
        return {"error": "SESSDATA environment variable is not set."}
        
    if not user_id and not username:
        return {"error": "Either user_id or username must be provided."}

    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}

    # 验证动态类型
    valid_types = ["ALL", "VIDEO", "ARTICLE", "ANIME"]
    if dynamic_type not in valid_types:
        return {"error": f"Dynamic type must be one of: {', '.join(valid_types)}"}

    try:
        # 使用统一的用户ID获取函数
        target_uid = get_user_id(user_id, username)
        if not target_uid:
            return {"error": "Failed to determine user_id."}

        # 创建用户对象
        u = user.User(uid=target_uid, credential=cred)
        
        # 获取用户信息
        user_info = sync(u.get_user_info())
        
        # 使用新的HTTP API方式获取动态
        dynamics = []
        offset = ""
        collected_count = 0
        
        # 循环获取动态直到达到限制数量或没有更多数据
        while collected_count < limit:
            # 获取一页动态数据
            data = fetch_dynamic_data(offset, str(target_uid))
            if not data:
                break
                
            # 解析动态数据
            page_dynamics, next_offset = parse_dynamic_data(data)
            if not page_dynamics:
                break
                
            # 添加到结果中
            for dyn in page_dynamics:
                if collected_count >= limit:
                    break
                dynamics.append(dyn)
                collected_count += 1
                
            # 检查是否还有更多数据
            if not next_offset:
                break
                
            offset = next_offset

        return {
            "user": {
                "mid": user_info.get("mid"),
                "name": user_info.get("name"),
                "face": user_info.get("face"),
                "sign": user_info.get("sign"),
                "level": user_info.get("level"),
            },
            "dynamics": dynamics,
            "count": len(dynamics)
        }
    except ApiException as e:
        return {"error": f"Bilibili API Error: {e.msg}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {str(e)}"}


@mcp.resource("bili://user/{user_id}")
def get_user_info_resource_endpoint(user_id: int) -> TextContent:
    """获取用户信息资源"""
    data = get_user_info_resource(user_id)
    return TextContent(type="text", text=json.dumps(data), mimeType="application/json")

@mcp.resource("bili://videos/{user_id}")
def get_user_videos_resource_endpoint(user_id: int, limit: int = 10) -> TextContent:
    """获取用户视频资源"""
    data = get_user_videos_resource(user_id, limit)
    return TextContent(type="text", text=json.dumps(data), mimeType="application/json")

@mcp.resource("bili://dynamics/{user_id}")
def get_user_dynamics_resource_endpoint(user_id: int, limit: int = 10, dynamic_type: str = "ALL") -> TextContent:
    """获取用户动态资源"""
    data = get_user_dynamics_resource(user_id, limit, dynamic_type)
    return TextContent(type="text", text=json.dumps(data), mimeType="application/json")

@mcp.resource("bili://schemas")
def get_data_schemas() -> TextContent:
    """获取数据结构schema，帮助模型理解输出格式"""
    schemas = {
        "video_schema": {
            "type": "object",
            "properties": {
                "bvid": {"type": "string", "description": "视频唯一标识"},
                "title": {"type": "string", "description": "视频标题"},
                "play": {"type": "integer", "description": "播放次数"},
                "duration": {"type": "string", "description": "视频时长"},
                "url": {"type": "string", "description": "视频完整URL"}
            },
            "required": ["bvid", "title"]
        },
        "dynamic_schema": {
            "type": "object",
            "properties": {
                "dynamic_id": {"type": "string", "description": "动态唯一标识"},
                "timestamp": {"type": "integer", "description": "发布时间戳"},
                "type": {"type": "string", "description": "动态类型"},
                "content": {"type": "object", "description": "动态内容"},
                "stat": {"type": "object", "description": "互动统计"}
            },
            "required": ["dynamic_id", "type"]
        }
    }
    return TextContent(type="text", text=json.dumps(schemas), mimeType="application/json")


# --- 提示预设 (用于规范模型输出格式) ---

@mcp.prompt()
def format_video_response(videos: str) -> str:
    """
    将视频数据转换为标准化的结构化输出格式。

    这个提示帮助模型以一致、易读的方式格式化视频信息。

    Args:
        videos: 包含视频数据的JSON字符串或文本

    Returns:
        规范化的视频信息说明
    """
    return f"""
基于以下视频数据，请将其组织为结构化的 markdown 格式：

**数据源**: {videos}

**输出格式要求**:
- 使用清晰的标题和分段
- 显示重要信息：标题、播放量、时长、BVID、发布日期
- 按播放量降序排列（如果有多个视频）
- 提供完整的视频URL链接
- 使用表格或列表显示，便于阅读
- 标记热门视频（播放量>10000）

请按照此格式重新组织并呈现视频信息。
"""

@mcp.prompt()
def format_dynamic_response(dynamics: str) -> str:
    """
    将用户动态数据转换为标准化的时间轴格式。

    这个提示帮助模型以时间顺序和类型分类的方式展示动态信息。

    Args:
        dynamics: 包含动态数据的JSON字符串或文本

    Returns:
        规范化的动态信息说明
    """
    return f"""
基于以下动态数据，请按时间轴和类型分类展示：

**数据源**: {dynamics}

**整理要求**:
- **时间轴显示**: 按发布时间倒序（最新优先）
- **类型分类**: 文本动态 🗣️、视频 🎥、图片 🖼️、文章 📝
- **关键信息**: 发布时间、互动数（点赞、评论、转发）、动态类型
- **内容摘要**: 为每个动态提供简要内容预览
- **热点标记**: 高互动量(>100点赞)的动态特别标注 ⭐

请以易读的格式呈现，并提供总体动态统计。
"""

@mcp.prompt()
def analyze_user_activity(user_info: str, recent_videos: str, recent_dynamics: str) -> str:
    """
    综合分析用户的创作活跃度。

    这个提示帮助模型从多个维度分析用户的创作和互动情况。

    Args:
        user_info: 用户基本信息
        recent_videos: 近期视频数据
        recent_dynamics: 近期动态数据

    Returns:
        用户创作活跃度分析说明
    """
    return f"""
请综合分析用户的创作活跃度和互动状况：

**用户信息**: {user_info}
**近期视频**: {recent_videos}
**近期动态**: {recent_dynamics}

**分析维度**:
1. **创作频率**: 视频发布间隔、动态更新频率
2. **内容偏好**: 主要创作类型（视频/图文/文章）
3. **互动热度**: 平均点赞、评论、播放数据
4. **发展趋势**: 近期活跃度趋势
5. **建议**: 基于数据给出的改进建议

请提供数据驱动的分析和有价值的洞察。
"""


def main():
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
