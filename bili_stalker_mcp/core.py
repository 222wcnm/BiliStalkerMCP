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
    """获取B站用户的详细资料。返回JSON对象，其中头像(face)和头图(top_photo)为Markdown格式。为保证数据完整，默认返回所有字段。"""
    try:
        u = user.User(uid=user_id, credential=cred)
        info = await u.get_user_info()
        if not info or 'mid' not in info:
            raise ValueError("User info response is invalid")

        face_url = info.get("face")
        top_photo_url = info.get("top_photo")

        user_data = {
            "mid": info.get("mid"),
            "name": info.get("name"),
            "face": f"![avatar]({face_url})" if face_url else "",
            "sign": info.get("sign"),
            "level": info.get("level"),
            "birthday": info.get("birthday"),
            "sex": info.get("sex"),
            "top_photo": f"![header]({top_photo_url})" if top_photo_url else "",
            "live_room": info.get("live_room"),
            "following": None,
            "follower": None
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
    """获取用户的视频列表。返回JSON列表，其中封面(pic)为Markdown格式。'subtitle'字段包含字幕对象，其'subtitles'列表内含可用于文本分析的字幕URL。"""
    try:
        u = user.User(uid=user_id, credential=cred)
        video_list = await u.get_videos(ps=limit)
        raw_videos = video_list.get("list", {}).get("vlist", [])
        processed_videos = []
        for v_data in raw_videos:
            pic_url = v_data.get("pic")
            processed_video = {
                "mid": v_data.get("mid"),
                "bvid": v_data.get("bvid"),
                "aid": v_data.get("aid"),
                "title": v_data.get("title"),
                "description": v_data.get("description"),
                "created": v_data.get("created"),
                "length": v_data.get("length"),
                "play": v_data.get("play"),
                "comment": v_data.get("comment"),
                "favorites": v_data.get("favorites"),
                "like": v_data.get("like"),
                "pic": f"![cover]({pic_url})" if pic_url else "",
                "subtitle": v_data.get("subtitle"),
                "url": f"https://www.bilibili.com/video/{v_data.get('bvid')}"
            }

            subtitle_obj = processed_video.get("subtitle")
            if not subtitle_obj or not isinstance(subtitle_obj, dict) or not subtitle_obj.get("subtitles"):
                processed_video["subtitle"] = "视频无字幕"
            
            processed_videos.append(processed_video)

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
    """获取用户的专栏文章列表。返回JSON列表，其中头图(banner_url)为Markdown格式。为保证数据完整，默认返回所有字段。"""
    try:
        u = user.User(uid=user_id, credential=cred)
        articles_data = await u.get_articles(ps=limit)
        
        raw_articles = articles_data.get("articles", [])
        processed_articles = []
        for article_data in raw_articles:
            if len(processed_articles) >= limit:
                break

            banner_url = article_data.get("banner_url")
            processed_article = {
                "mid": article_data.get("author", {}).get("mid"),
                "id": article_data.get("id"),
                "title": article_data.get("title"),
                "summary": article_data.get("summary"),
                "banner_url": f"![banner]({banner_url})" if banner_url else "",
                "publish_time": article_data.get("publish_time"),
                "stats": article_data.get("stats"),
                "words": article_data.get("words"),
                "url": f"https://www.bilibili.com/read/cv{article_data.get('id')}"
            }
            processed_articles.append(processed_article)
            
        return {"articles": processed_articles}
    except ApiException as e:
        logger.error(f"Bilibili API error for articles of UID {user_id}: {e}")
        return {"error": f"Bilibili API 错误: {str(e)}"}
    except Exception as e:
        logger.error(f"Failed to get user articles for UID {user_id}: {e}")
        return {"error": f"获取用户专栏文章失败: {str(e)}"}