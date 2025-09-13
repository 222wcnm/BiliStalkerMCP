import logging
import os
import asyncio
import json
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

def _parse_dynamic_item(item: dict) -> dict:
    """将单个动态的原始字典数据解析为干净的目标格式。"""
    try:
        desc = item.get('desc', {})
        card = item.get('card', {}) # It's a dict now, not a string.

        # Base structure from 'desc'
        parsed = {
            "dynamic_id": desc.get('dynamic_id_str'),
            "type_id": desc.get('type'),
            "author_mid": desc.get('uid'),
            "timestamp": desc.get('timestamp'),
            "stats": {
                "like": desc.get('like'),
                "comment": desc.get('comment'),
                "forward": desc.get('repost'),
            }
        }

        # --- Content Extraction ---
        dynamic_type = desc.get('type')
        
        # Type 1: Repost
        if dynamic_type == 1:
            parsed['type'] = 'REPOST'
            parsed['text_content'] = card.get('item', {}).get('content')
            if 'origin' in card:
                try:
                    # Origin is a JSON string inside the card dict
                    origin_card = json.loads(card['origin'])
                    origin_item = origin_card.get('item', {})
                    parsed['origin_user'] = origin_card.get('user', {}).get('uname')
                    parsed['origin_content'] = origin_item.get('content') or origin_item.get('description')
                except Exception:
                    parsed['origin_content'] = "(转发内容解析失败)"

        # Type 2: Image-text
        elif dynamic_type == 2:
            parsed['type'] = 'IMAGE_TEXT'
            item_data = card.get('item', {})
            parsed['text_content'] = item_data.get('description')
            parsed['images'] = [p.get('img_src') for p in item_data.get('pictures', [])]

        # Type 4: Text-only
        elif dynamic_type == 4:
            parsed['type'] = 'TEXT'
            parsed['text_content'] = card.get('item', {}).get('content')

        # Type 8: Video
        elif dynamic_type == 8:
            parsed['type'] = 'VIDEO'
            parsed['text_content'] = card.get('dynamic')
            parsed['video'] = {
                "title": card.get('title'),
                "bvid": card.get('bvid'),
                "desc": card.get('desc'),
                "pic": card.get('pic')
            }

        # Type 64: Article
        elif dynamic_type == 64:
            parsed['type'] = 'ARTICLE'
            parsed['text_content'] = card.get('summary')
            parsed['article'] = {
                "id": card.get('id'),
                "title": card.get('title'),
                "covers": card.get('image_urls', [])
            }
        
        # Type 2048: Charge/QA post (the one from our test)
        elif dynamic_type == 2048:
            parsed['type'] = 'CHARGE_QA'
            parsed['text_content'] = card.get('vest', {}).get('content')
            if 'sketch' in card:
                parsed['text_content'] += f" | {card['sketch'].get('title')}"
        
        else:
            parsed['type'] = f"UNKNOWN_{dynamic_type}"
            parsed['text_content'] = '(内容无法解析)'

        return parsed
    except Exception as e:
        logger.error(f"Failed to parse dynamic item: {item.get('desc', {}).get('dynamic_id_str')}, error: {e}")
        return {"error": "Failed to parse dynamic", "id": item.get('desc', {}).get('dynamic_id_str')}

@alru_cache(maxsize=128, ttl=3600)
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

@alru_cache(maxsize=32, ttl=300)
async def fetch_user_info(user_id: int, cred: Credential) -> Dict[str, Any]:
    """获取B站用户的详细资料。返回JSON对象，为保证数据完整，默认返回所有字段。"""
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
            "birthday": info.get("birthday"),
            "sex": info.get("sex"),
            "top_photo": info.get("top_photo"),
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

async def fetch_user_videos(user_id: int, page: int, limit: int, cred: Credential) -> Dict[str, Any]:
    """获取用户的视频列表。'subtitle'字段包含字幕对象，其'subtitles'列表内含可用于文本分析的字幕URL。"""
    try:
        u = user.User(uid=user_id, credential=cred)
        video_list = await u.get_videos(pn=page, ps=limit)
        raw_videos = video_list.get("list", {}).get("vlist", [])
        processed_videos = []
        for v_data in raw_videos:
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
                "pic": v_data.get("pic"),
                "subtitle": v_data.get("subtitle"),
                "url": f"https://www.bilibili.com/video/{v_data.get('bvid')}"
            }
            processed_videos.append(processed_video)

        return {"videos": processed_videos, "total": video_list.get("page", {}).get("count", 0)}
    except ApiException as e:
        logger.error(f"Bilibili API error for videos of UID {user_id}: {e}")
        return {"error": f"Bilibili API 错误: {str(e)}"}
    except Exception as e:
        logger.error(f"Failed to get user videos for UID {user_id}: {e}")
        return {"error": f"获取用户视频时发生未知错误: {str(e)}"}

async def fetch_user_dynamics(user_id: int, offset: int, limit: int, cred: Credential, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """获取用户的动态列表。为保证数据可用性，返回JSON列表。会尝试解析不同类型的动态。"""
    try:
        u = user.User(uid=user_id, credential=cred)
        raw_dynamics_data = await u.get_dynamics(offset=offset)
        
        processed_dynamics = []
        if raw_dynamics_data and raw_dynamics_data.get("cards"):
            for card in raw_dynamics_data["cards"]:
                if len(processed_dynamics) >= limit:
                    break
                processed_dynamics.append(_parse_dynamic_item(card))

        return {"dynamics": processed_dynamics}
    except ApiException as e:
        logger.error(f"Bilibili API error for dynamics of UID {user_id}: {e}")
        return {"error": f"Bilibili API 错误: {str(e)}"}
    except Exception as e:
        logger.error(f"An unexpected error in fetch_user_dynamics for UID {user_id}: {e}")
        return {"error": f"处理动态数据时发生未知错误: {str(e)}"}

async def fetch_user_articles(user_id: int, page: int, limit: int, cred: Credential) -> Dict[str, Any]:
    """获取用户的专栏文章列表。为保证数据完整，默认返回所有字段。"""
    try:
        u = user.User(uid=user_id, credential=cred)
        articles_data = await u.get_articles(pn=page, ps=limit)
        
        raw_articles = articles_data.get("articles", [])
        processed_articles = []
        for article_data in raw_articles:
            if len(processed_articles) >= limit:
                break

            processed_article = {
                "mid": article_data.get("author", {}).get("mid"),
                "id": article_data.get("id"),
                "title": article_data.get("title"),
                "summary": article_data.get("summary"),
                "banner_url": article_data.get("banner_url"),
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
        return {"error": f"获取用户专栏文章时发生未知错误: {str(e)}"}


async def fetch_user_followings(user_id: int, page: int, limit: int, cred: Credential) -> Dict[str, Any]:
    """获取用户的关注列表。"""
    try:
        api_url = "https://api.bilibili.com/x/relation/followings"
        params = {'vmid': user_id, 'ps': limit, 'pn': page}
        headers = DEFAULT_HEADERS.copy()
        headers['Cookie'] = _get_cookies(cred)
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, params=params, headers=headers, timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT))
            response.raise_for_status()
            followings_data = response.json()
            if followings_data.get('code') == 2207:
                return {"error": "用户关注列表已设置为隐私"}
            if followings_data.get('code') != 0:
                raise ApiException(msg=followings_data.get('message', 'Failed to fetch followings from raw API.'))
            followings_data = followings_data.get('data', {})

        raw_followings = followings_data.get("list", [])
        processed_followings = []
        for f_data in raw_followings:
            processed_following = {
                "mid": f_data.get("mid"),
                "uname": f_data.get("uname"),
                "face": f_data.get("face"),
                "sign": f_data.get("sign"),
                "official_verify": f_data.get("official_verify", {}).get("desc"),
                "vip_type": f_data.get("vip", {}).get("vipType")
            }
            processed_followings.append(processed_following)

        return {"followings": processed_followings, "total": followings_data.get("total", 0)}

    except ApiException as e:
        logger.error(f"Bilibili API error for followings of UID {user_id}: {e}")
        return {"error": f"Bilibili API 错误: {str(e)}"}
    except httpx.RequestError as e:
        logger.error(f"Network error for followings of UID {user_id}: {e}")
        return {"error": f"网络错误: {str(e)}"}
    except Exception as e:
        logger.error(f"Failed to get user followings for UID {user_id}: {e}")
        return {"error": f"获取用户关注列表时发生未知错误: {str(e)}"}