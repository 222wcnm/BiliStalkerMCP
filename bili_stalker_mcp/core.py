import logging
import os
import asyncio
from datetime import datetime, timezone
import random
from typing import Any, Dict, Optional

import httpx
import bilibili_api
from bilibili_api import Credential, user, search
from bilibili_api.exceptions import ApiException
from async_lru import alru_cache

from .config import (
    DEFAULT_HEADERS, REQUEST_DELAY, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX,
    REQUEST_TIMEOUT, CONNECT_TIMEOUT, READ_TIMEOUT
)

# 配置 bilibili-api 请求设置
bilibili_api.request_settings.set('headers', DEFAULT_HEADERS)
bilibili_api.request_settings.set('timeout', REQUEST_TIMEOUT)

logger = logging.getLogger(__name__)

def get_credential(sessdata: str, bili_jct: str, buvid3: str) -> Optional[Credential]:
    """创建Bilibili API的凭证对象"""
    if not sessdata:
        logger.error("SESSDATA environment variable is not set or empty.")
        return None
    return Credential(sessdata=sessdata, bili_jct=bili_jct, buvid3=buvid3)

def _get_cookies(cred: Credential) -> str:
    """获取用于请求的 Cookie 字符串。"""
    cookie_parts = []
    if getattr(cred, "sessdata", None):
        cookie_parts.append(f"SESSDATA={cred.sessdata}")
    if getattr(cred, "bili_jct", None):
        cookie_parts.append(f"bili_jct={cred.bili_jct}")
    if getattr(cred, "buvid3", None):
        cookie_parts.append(f"buvid3={cred.buvid3}")
    return "; ".join(cookie_parts)

@alru_cache(maxsize=128)
async def get_user_id_by_username(username: str) -> Optional[int]:
    """通过用户名搜索并获取用户ID"""
    if not username:
        return None
    try:
        search_result = await search.search_by_type(
            keyword=username,
            search_type=search.SearchObjectType.USER
        )
        result_list = search_result.get("result") or (search_result.get("data", {}) or {}).get("result")
        if not isinstance(result_list, list) or not result_list:
            logger.warning(f"User '{username}' not found in search results.")
            return None
        return result_list[0]['mid']
    except ApiException as e:
        logger.error(f"Bilibili API error while searching for user '{username}': {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while searching for user '{username}': {e}")
        return None

@alru_cache(maxsize=32)
async def fetch_user_info(user_id: int, cred: Credential) -> Dict[str, Any]:
    """获取并处理B站用户信息"""
    try:
        u = user.User(uid=user_id, credential=cred)
        info = await u.get_user_info()
        if not info or 'mid' not in info:
            raise ValueError("User info response is invalid")

        user_data = {
            "mid": info.get("mid"),
            "name": info.get("name"),
            "face": info.get("face"),
            "sign": info.get("sign"),
            "level": info.get("level"),
            "following": None, 
            "follower": None, 
            "birthday": info.get("birthday"),
            "sex": info.get("sex"),
            "vip": info.get("vip"),
            "official": info.get("official"),
            "top_photo": info.get("top_photo"),
            "live_room": info.get("live_room")
        }

        try:
            stat_url = "https://api.bilibili.com/x/relation/stat"
            params = {'vmid': user_id}
            headers = DEFAULT_HEADERS.copy()
            headers['Cookie'] = _get_cookies(cred)
            
            async with httpx.AsyncClient() as client:
                response = await client.get(stat_url, params=params, headers=headers, timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT))
                response.raise_for_status()
                stat_data = response.json()

            if stat_data.get('code') == 0 and 'data' in stat_data:
                user_data['following'] = stat_data['data'].get('following')
                user_data['follower'] = stat_data['data'].get('follower')
            else:
                logger.warning(f"Failed to get relation stat for UID {user_id}: {stat_data.get('message')}")
        except httpx.RequestError as e:
            logger.warning(f"HTTP request for relation stat failed for UID {user_id}: {e}")
        
        return user_data

    except ApiException as e:
        logger.error(f"Bilibili API error for UID {user_id}: {e}")
        return {"error": f"Bilibili API 错误: {str(e)}"}
    except httpx.RequestError as e:
        logger.error(f"Network error for UID {user_id}: {e}")
        return {"error": f"网络错误: {str(e)}"}
    except Exception as e:
        logger.error(f"Failed to get user info for UID {user_id}: {e}")
        return {"error": f"获取用户信息时发生未知错误: {str(e)}"}

async def fetch_user_videos(user_id: int, limit: int, cred: Credential) -> Dict[str, Any]:
    """获取并处理用户视频列表"""
    try:
        u = user.User(uid=user_id, credential=cred)
        video_list = await u.get_videos(ps=limit)
        raw_videos = video_list.get("list", {}).get("vlist", [])
        processed_videos = []
        for v_data in raw_videos:
            publish_time = datetime.fromtimestamp(v_data.get("created"), tz=timezone.utc).isoformat() if v_data.get("created") else None
            processed_videos.append({
                "bvid": v_data.get("bvid"),
                "title": v_data.get("title"),
                "description": v_data.get("description"),
                "created": publish_time,
                "length": v_data.get("length"),
                "play": v_data.get("play"),
                "url": f"https://www.bilibili.com/video/{v_data.get('bvid')}",
            })
        return {"videos": processed_videos, "total": video_list.get("page", {}).get("count", 0)}
    except ApiException as e:
        logger.error(f"Bilibili API error for videos of UID {user_id}: {e}")
        return {"error": f"Bilibili API 错误: {str(e)}"}
    except Exception as e:
        logger.error(f"Failed to get user videos for UID {user_id}: {e}")
        return {"error": f"获取用户视频失败: {str(e)}"}

async def fetch_user_dynamics(user_id: int, limit: int, cred: Credential, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """获取用户动态列表"""
    try:
        u = user.User(uid=user_id, credential=cred)
        dynamics_data = await u.get_dynamics()
        # 注意：直接返回库处理好的数据，其中可能包含比我们手动解析更丰富的信息
        # 我们可以在cli层或调用方进行瘦身
        return dynamics_data
    except ApiException as e:
        logger.error(f"Bilibili API error for dynamics of UID {user_id}: {e}")
        return {"error": f"Bilibili API 错误: {str(e)}"}
    except Exception as e:
        logger.error(f"An unexpected error in fetch_user_dynamics for UID {user_id}: {e}")
        return {"error": f"处理动态数据时发生未知错误: {str(e)}"}

async def fetch_user_articles(user_id: int, limit: int, cred: Credential) -> Dict[str, Any]:
    """获取用户专栏文章列表"""
    try:
        u = user.User(uid=user_id, credential=cred)
        articles_data = await u.get_articles(ps=limit)
        
        raw_articles = articles_data.get("articles", [])
        processed_articles = []
        for article_data in raw_articles:
            if len(processed_articles) >= limit:
                break
            
            publish_time = None
            publish_timestamp = article_data.get("publish_time")
            if publish_timestamp:
                try:
                    publish_time = datetime.fromtimestamp(publish_timestamp, tz=timezone.utc).isoformat()
                except (ValueError, OSError) as e:
                    logger.warning(f"Invalid timestamp for article {article_data.get('id')}: {e}")

            processed_articles.append({
                "id": article_data.get("id"),
                "title": article_data.get("title"),
                "summary": article_data.get("summary"),
                "banner_url": article_data.get("banner_url"),
                "publish_time": publish_time,
                "view": article_data.get("stats", {}).get("view", 0),
                "like": article_data.get("stats", {}).get("like", 0),
                "comment": article_data.get("stats", {}).get("reply", 0),
                "url": f"https://www.bilibili.com/read/cv{article_data.get('id')}"
            })
            
        return {"articles": processed_articles}
    except ApiException as e:
        logger.error(f"Bilibili API error for articles of UID {user_id}: {e}")
        return {"error": f"Bilibili API 错误: {str(e)}"}
    except Exception as e:
        logger.error(f"Failed to get user articles for UID {user_id}: {e}")
        return {"error": f"获取用户专栏文章失败: {str(e)}"}