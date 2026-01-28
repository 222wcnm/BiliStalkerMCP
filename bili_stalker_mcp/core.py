import logging
import os
import json
import random
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
import bilibili_api
from bilibili_api import Credential, user, search, video, aid2bvid
from bilibili_api.exceptions import ApiException
from async_lru import alru_cache

# 导入配置（会自动初始化 bilibili-api 反爬设置）
from .config import (
    DEFAULT_HEADERS, REQUEST_DELAY,
    REQUEST_TIMEOUT, CONNECT_TIMEOUT, READ_TIMEOUT
)
# 导入统一重试装饰器
from .retry import with_retry

# 配置 bilibili-api 请求设置（headers 和 timeout）
bilibili_api.request_settings.set('headers', DEFAULT_HEADERS)
bilibili_api.request_settings.set('timeout', REQUEST_TIMEOUT)

logger = logging.getLogger(__name__)

def get_credential() -> Optional[Credential]:
    """从环境变量创建Bilibili API的凭证对象"""
    sessdata = os.environ.get("SESSDATA")
    bili_jct = os.environ.get("BILI_JCT")
    buvid3 = os.environ.get("BUVID3")

    if not sessdata:
        logger.error("SESSDATA is not set in environment variables.")
        return None

    # 智能认证级别
    try:
        if bili_jct and buvid3:
            logger.debug("Using full authentication (SESSDATA + BILI_JCT + BUVID3)")
            return Credential(sessdata=sessdata, bili_jct=bili_jct, buvid3=buvid3)
        elif bili_jct:
            logger.debug("Using partial authentication (SESSDATA + BILI_JCT)")
            return Credential(sessdata=sessdata, bili_jct=bili_jct, buvid3="")
        else:
            logger.warning("Using minimal authentication (SESSDATA only) - some features may be limited")
            return Credential(sessdata=sessdata, bili_jct="", buvid3="")
    except Exception as e:
        logger.error(f"Failed to create credential object: {e}")
        return None

def _format_timestamp(ts: int | None) -> str | None:
    """将时间戳转换为可读的日期时间格式"""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return None

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

async def _get_video_subtitle_info(bvid: str, cred: Credential) -> Dict[str, Any]:
    """获取视频的详细字幕信息（优化版）
    
    使用 get_player_info 作为主要方法，因为它能返回包括 AI 字幕在内的完整字幕列表。
    Bilibili 的 x/web-interface/view API 不再返回完整字幕信息。
    """
    try:
        if not bvid:
            return {"has_subtitle": False, "subtitle_count": 0, "subtitle_list": []}
            
        v = video.Video(bvid=bvid, credential=cred)
        
        subtitle_info = {
            "has_subtitle": False,
            "subtitle_count": 0,
            "subtitle_list": [],
            "subtitle_summary": "无字幕"
        }
        
        subtitles_data = None
        
        # 方法1（主要）：使用 get_player_info 获取字幕，这是最可靠的方式
        # 因为它调用的是 x/player/v2 端点，能返回完整的字幕列表（包括AI字幕）
        try:
            pages = await v.get_pages()
            if pages:
                cid = pages[0].get('cid')
                if cid:
                    # 使用 get_player_info 获取播放器信息，包含字幕
                    player_info = await v.get_player_info(cid=cid)
                    subtitles_data = player_info.get("subtitle", {}).get("subtitles", [])
                    if subtitles_data:
                        logger.debug(f"Using get_player_info method for video {bvid}, found {len(subtitles_data)} subtitles")
        except Exception as e:
            logger.debug(f"get_player_info method failed for video {bvid}: {e}")
        
        # 方法2（备选）：尝试从视频基本信息获取（可能不包含AI字幕）
        if not subtitles_data:
            try:
                video_info = await v.get_info()
                subtitles_data = video_info.get("subtitle", {}).get("list", [])
                if subtitles_data:
                    logger.debug(f"Using video info method for video {bvid}, found {len(subtitles_data)} subtitles")
            except Exception as e:
                logger.debug(f"get_info method failed for video {bvid}: {e}")
        
        # 方法3（备选）：使用 get_subtitle 方法
        if not subtitles_data:
            try:
                pages = await v.get_pages()
                if pages:
                    cid = pages[0].get('cid')
                    if cid:
                        subtitle_response = await v.get_subtitle(cid=cid)
                        subtitles_data = subtitle_response.get("subtitles", [])
                        if subtitles_data:
                            logger.debug(f"Using get_subtitle method for video {bvid}, found {len(subtitles_data)} subtitles")
            except Exception as e:
                logger.debug(f"get_subtitle method failed for video {bvid}: {e}")
        
        # 处理字幕数据
        if subtitles_data:
            subtitle_info["has_subtitle"] = True
            subtitle_info["subtitle_count"] = len(subtitles_data)
            
            logger.debug(f"Found {len(subtitles_data)} subtitle tracks for video {bvid}")
            
            # 收集语言信息用于概要
            languages = []
            
            for sub in subtitles_data:
                # 处理AI字幕的特殊情况
                is_ai_generated = False
                lan_code = sub.get("lan", "")
                if lan_code.startswith("ai-") or sub.get("ai_type", 0) > 0 or sub.get("ai_status", 0) > 0:
                    is_ai_generated = True
                
                subtitle_item = {
                    "id": sub.get("id"),
                    "lan": lan_code,
                    "lan_doc": sub.get("lan_doc"),
                    "author_mid": sub.get("author", {}).get("mid") if sub.get("author") else None,
                    "author_name": sub.get("author", {}).get("name") if sub.get("author") else None,
                    "subtitle_url": sub.get("subtitle_url"),
                    "is_ai_generated": is_ai_generated
                }
                subtitle_info["subtitle_list"].append(subtitle_item)
                
                # 收集语言信息
                lang_desc = sub.get("lan_doc", sub.get("lan", "未知"))
                if is_ai_generated:
                    lang_desc += "(AI生成)"
                languages.append(lang_desc)
            
            # 生成简洁的字幕概要
            if languages:
                subtitle_info["subtitle_summary"] = f"有{len(languages)}种字幕: " + ", ".join(languages)
            
            logger.debug(f"Video {bvid} subtitle summary: {subtitle_info['subtitle_summary']}")
        else:
            logger.debug(f"No subtitles found for video {bvid}")
        
        return subtitle_info
        
    except Exception as e:
        logger.warning(f"Failed to get subtitle info for video {bvid}: {e}")
        return {
            "has_subtitle": False, 
            "subtitle_count": 0, 
            "subtitle_list": [], 
            "subtitle_summary": "获取失败",
            "error": str(e)
        }

def _parse_dynamic_item(item: dict) -> dict:
    """将单个动态的原始字典数据解析为干净的目标格式。"""
    try:
        desc = item.get('desc', {})
        card = item.get('card', {}) # It's a dict now, not a string.

        # Base structure from 'desc'
        timestamp = desc.get('timestamp')
        parsed = {
            "dynamic_id": desc.get('dynamic_id_str'),
            "timestamp": timestamp,
            "publish_time": _format_timestamp(timestamp)
        }

        # --- Content Extraction ---
        dynamic_type = desc.get('type')
        
        # Type 1: Repost
        if dynamic_type == 1:
            parsed['type'] = 'REPOST'
            parsed['text_content'] = card.get('item', {}).get('content')
            
            # 解析被转发的原始内容
            origin_card = card.get('origin')
            origin_type = desc.get('origin', {}).get('type')
            origin_user = card.get('origin_user', {}).get('info', {})
            
            if origin_card and isinstance(origin_card, dict):
                origin_info = {
                    "user_name": origin_user.get('uname'),
                    "user_id": origin_user.get('uid')
                }
                
                # 常见类型完整解析
                if origin_type == 8:  # VIDEO
                    origin_info["type"] = "VIDEO"
                    origin_info["text_content"] = origin_card.get('dynamic')
                    origin_info["video"] = {
                        "title": origin_card.get('title'),
                        "bvid": origin_card.get('bvid') or (aid2bvid(origin_card.get('aid')) if origin_card.get('aid') else None),
                        "pic": origin_card.get('pic')
                    }
                elif origin_type == 2:  # IMAGE_TEXT
                    origin_item = origin_card.get('item', {})
                    pictures = origin_item.get('pictures') or []
                    image_urls = [p.get('img_src') for p in pictures if isinstance(p, dict)]
                    origin_info["type"] = "IMAGE_TEXT" if image_urls else "TEXT"
                    origin_info["text_content"] = origin_item.get('description')
                    if image_urls:
                        origin_info["images"] = image_urls
                elif origin_type == 4:  # TEXT
                    origin_info["type"] = "TEXT"
                    origin_info["text_content"] = origin_card.get('item', {}).get('content')
                elif origin_type == 64:  # ARTICLE
                    origin_info["type"] = "ARTICLE"
                    origin_info["text_content"] = origin_card.get('summary')
                    origin_info["article"] = {
                        "id": origin_card.get('id'),
                        "title": origin_card.get('title')
                    }
                else:
                    # 非常见类型：只提取文字摘要
                    origin_info["type"] = f"OTHER_{origin_type}"
                    origin_info["text_content"] = (
                        origin_card.get('title') or 
                        origin_card.get('description') or 
                        origin_card.get('content') or 
                        origin_card.get('summary') or
                        origin_card.get('vest', {}).get('content') or
                        "(无文字内容)"
                    )
                
                parsed['origin'] = origin_info

        # Type 2: Image-text (或无图时视为纯文字)
        elif dynamic_type == 2:
            item_data = card.get('item', {})
            parsed['text_content'] = item_data.get('description')
            # 检查是否有图片
            pictures = item_data.get('pictures') or []
            image_urls = [p.get('img_src') for p in pictures if isinstance(p, dict)]
            if image_urls:
                parsed['type'] = 'IMAGE_TEXT'
                parsed['images'] = image_urls
            else:
                # 没有图片时视为纯文字动态
                parsed['type'] = 'TEXT'

        # Type 4: Text-only
        elif dynamic_type == 4:
            parsed['type'] = 'TEXT'
            parsed['text_content'] = card.get('item', {}).get('content')

        # Type 8: Video
        elif dynamic_type == 8:
            parsed['type'] = 'VIDEO'
            parsed['text_content'] = card.get('dynamic')
            
            # 修复视频bvid字段 - 如果为空则从aid转换生成
            video_bvid = card.get('bvid')
            video_aid = card.get('aid')
            
            if not video_bvid and video_aid:
                try:
                    video_bvid = aid2bvid(video_aid)
                    logger.debug(f"Generated bvid {video_bvid} from aid {video_aid} in dynamic")
                except Exception as e:
                    logger.warning(f"Failed to convert aid {video_aid} to bvid in dynamic: {e}")
                    video_bvid = None
            
            parsed['video'] = {
                "title": card.get('title'),
                "bvid": video_bvid
            }

        # Type 64: Article
        elif dynamic_type == 64:
            parsed['type'] = 'ARTICLE'
            parsed['text_content'] = card.get('summary')
            parsed['article'] = {
                "id": card.get('id'),
                "title": card.get('title')
            }
        
        # Type 2048: Charge/QA post (增强解析)
        elif dynamic_type == 2048:
            parsed['type'] = 'CHARGE_QA'
            vest_content = card.get('vest', {}).get('content', '')
            sketch_title = card.get('sketch', {}).get('title', '')
            parsed['text_content'] = f"{vest_content} {sketch_title}".strip()
            parsed['charge_info'] = {
                "vest": card.get('vest', {}),
                "sketch": card.get('sketch', {})
            }
        
        # Type 512: Activity/番剧
        elif dynamic_type == 512:
            parsed['type'] = 'ACTIVITY'
            parsed['text_content'] = card.get('title', '') or card.get('description', '')
            parsed['activity_info'] = {
                "title": card.get('title'),
                "description": card.get('description')
            }
        
        else:
            parsed['type'] = f"UNKNOWN_{dynamic_type}"
            parsed['text_content'] = f'(未支持的动态类型 {dynamic_type})'

        return parsed
    except Exception as e:
        dynamic_id = item.get('desc', {}).get('dynamic_id_str', 'unknown')
        dynamic_type = item.get('desc', {}).get('type', 'unknown')
        logger.error(f"Failed to parse dynamic item {dynamic_id} (type {dynamic_type}): {e}")
        
        # 增强的调试信息
        debug_info = {
            "error": f"Failed to parse dynamic: {str(e)}", 
            "id": dynamic_id,
            "type_id": dynamic_type,
            "error_location": f"Type {dynamic_type} parsing",
            "card_keys": list(item.get('card', {}).keys()) if item.get('card') else [],
            "desc_keys": list(item.get('desc', {}).keys()) if item.get('desc') else [],
            "raw_data_sample": str(item)[:300] + "..." if len(str(item)) > 300 else str(item)
        }
        
        return debug_info

@alru_cache(maxsize=128, ttl=3600)
@with_retry(max_retries=5, base_delay=2.0, return_default=True, default_on_exhaust=None)
async def get_user_id_by_username(username: str) -> Optional[int]:
    """通过用户名搜索并获取用户ID
    
    优先返回用户名精确匹配的结果，找不到时返回搜索排名第一的结果。
    使用 @with_retry 装饰器自动处理反爬重试。
    """
    if not username:
        return None
    
    search_result = await search.search_by_type(
        keyword=username,
        search_type=search.SearchObjectType.USER
    )
    result_list = search_result.get("result") or (search_result.get("data", {}) or {}).get("result")
    if not isinstance(result_list, list) or not result_list:
        logger.warning(f"User '{username}' not found in search results.")
        return None
    
    # 优先寻找用户名精确匹配的结果（忽略大小写）
    username_lower = username.lower()
    for user_item in result_list:
        uname = user_item.get('uname', '')
        if uname.lower() == username_lower:
            logger.debug(f"Found exact match for '{username}': UID {user_item['mid']}")
            return user_item['mid']
    
    # 找不到精确匹配，返回第一个结果并警告
    logger.warning(f"No exact match for '{username}', using first result: {result_list[0].get('uname')}")
    return result_list[0]['mid']

@alru_cache(maxsize=32, ttl=300)
@with_retry(max_retries=3, base_delay=2.0, return_default=True, default_on_exhaust={"error": "All retry attempts failed"})
async def fetch_user_info(user_id: int, cred: Credential) -> Dict[str, Any]:
    """获取B站用户的详细资料。返回JSON对象，为保证数据完整，默认返回所有字段。
    
    使用 @with_retry 装饰器自动处理反爬重试。
    """
    try:
        u = user.User(uid=user_id, credential=cred)
        info = await u.get_user_info()
        if not info or 'mid' not in info:
            raise ValueError("User info response is invalid")

        user_data = {
            "mid": info.get("mid"),
            "name": info.get("name"),
            "sign": info.get("sign"),
            "following": None,
            "follower": None
        }

        # 获取关注/粉丝数（非关键，失败不影响主流程）
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
        error_code = getattr(e, 'code', None)
        # 不可重试的错误码，直接返回错误信息
        if error_code == -404:
            return {"error": f"用户 {user_id} 不存在或已注销"}
        elif error_code == -509:
            return {"error": "请求过于频繁，被系统限流，请逐渐减少请求频率"}
        # 可重试的错误（-412），让装饰器处理
        raise

@with_retry(max_retries=3, base_delay=2.0, return_default=True, default_on_exhaust={"error": "All retry attempts failed"})
async def fetch_user_videos(user_id: int, page: int, limit: int, cred: Credential) -> Dict[str, Any]:
    """获取用户的视频列表。现在包含增强的字幕信息，包括字幕语言、作者和下载URL等详细信息。
    
    使用 @with_retry 装饰器自动处理反爬重试。
    """
    u = user.User(uid=user_id, credential=cred)
    video_list = await u.get_videos(pn=page, ps=limit)
    raw_videos = video_list.get("list", {}).get("vlist", [])
    processed_videos = []
    
    for v_data in raw_videos:
        # 修复 bvid 字段 - 如果为空则从 aid 转换生成
        bvid = v_data.get("bvid")
        aid = v_data.get("aid")
        
        if not bvid and aid:
            try:
                bvid = aid2bvid(aid)
                logger.debug(f"Generated bvid {bvid} from aid {aid}")
            except Exception as e:
                logger.warning(f"Failed to convert aid {aid} to bvid: {e}")
                bvid = None
        
        # 获取详细的字幕信息（只有当 bvid 存在时才获取）
        if bvid:
            subtitle_info = await _get_video_subtitle_info(bvid, cred)
        else:
            subtitle_info = {"has_subtitle": False, "subtitle_count": 0, "subtitle_list": [], "error": "No bvid available"}
        
        processed_video = {
            "bvid": bvid,
            "title": v_data.get("title"),
            "pic": v_data.get("pic"),
            "description": v_data.get("description"),
            "created": v_data.get("created"),
            "created_time": _format_timestamp(v_data.get("created")),
            "play": v_data.get("play"),
            "like": v_data.get("like"),
            "subtitle": {
                "has_subtitle": subtitle_info.get("has_subtitle", False),
                "subtitle_summary": subtitle_info.get("subtitle_summary", "无字幕")
            }
        }
        processed_videos.append(processed_video)

    return {"videos": processed_videos, "total": video_list.get("page", {}).get("count", 0)}

async def fetch_user_dynamics(user_id: int, offset: int, limit: int, cred: Credential, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """获取用户的动态列表。为保证数据可用性，返回JSON列表。会尝试解析不同类型的动态。"""
    try:
        # 导入DynamicType配置
        from .config import DynamicType
        
        u = user.User(uid=user_id, credential=cred)
        raw_dynamics_data = await u.get_dynamics(offset=offset)
        
        processed_dynamics = []
        if raw_dynamics_data and raw_dynamics_data.get("cards"):
            for card in raw_dynamics_data["cards"]:
                if len(processed_dynamics) >= limit:
                    break
                    
                parsed_item = _parse_dynamic_item(card)
                
                # 实现动态类型筛选
                item_type_id = card.get('desc', {}).get('type')
                
                # 默认只返回有分析价值的类型: TEXT(4), IMAGE_TEXT(2), REPOST(1)
                # 过滤掉 VIDEO(8) 和 ARTICLE(64) 因为有专门的工具获取
                valuable_types = [1, 2, 4]  # REPOST, IMAGE_TEXT, TEXT
                
                if dynamic_type == "ALL":
                    # 默认只返回有分析价值的类型
                    if item_type_id not in valuable_types:
                        continue
                elif dynamic_type == "ALL_RAW":
                    # 返回所有类型（包括 VIDEO/ARTICLE）
                    pass
                elif dynamic_type == "VIDEO" and item_type_id != 8:
                    continue
                elif dynamic_type == "ARTICLE" and item_type_id != 64:
                    continue
                elif dynamic_type == "DRAW" and item_type_id != 2:
                    continue
                elif dynamic_type == "TEXT" and item_type_id != 4:
                    continue
                        
                processed_dynamics.append(parsed_item)

        return {"dynamics": processed_dynamics, "total_fetched": len(processed_dynamics), "filter_type": dynamic_type}
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
                "id": article_data.get("id"),
                "title": article_data.get("title"),
                "summary": article_data.get("summary"),
                "publish_time": article_data.get("publish_time"),
                "publish_time_str": _format_timestamp(article_data.get("publish_time")),
                "stats": article_data.get("stats")
            }
            processed_articles.append(processed_article)
            
        return {"articles": processed_articles}
    except ApiException as e:
        logger.error(f"Bilibili API error for articles of UID {user_id}: {e}")
        return {"error": f"Bilibili API 错误: {str(e)}"}
    except Exception as e:
        logger.error(f"Failed to get user articles for UID {user_id}: {e}")
        return {"error": f"获取用户专栏文章时发生未知错误: {str(e)}"}


@with_retry(max_retries=3, base_delay=2.0, return_default=True, default_on_exhaust={"error": "All retry attempts failed"})
async def fetch_user_followings(user_id: int, page: int, limit: int, cred: Credential) -> Dict[str, Any]:
    """获取用户的关注列表。
    
    使用 @with_retry 装饰器自动处理反爬重试。
    """
    api_url = "https://api.bilibili.com/x/relation/followings"
    params = {'vmid': user_id, 'ps': limit, 'pn': page}
    headers = DEFAULT_HEADERS.copy()
    headers['Cookie'] = _get_cookies(cred)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(api_url, params=params, headers=headers, timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT))
        response.raise_for_status()
        followings_data = response.json()
        
        # 处理特殊错误码（不可重试）
        error_code = followings_data.get('code')
        if error_code == -509:
            return {"error": "请求过于频繁，被系统限流，请逐渐减少请求频率"}
        elif error_code in [2207, 22115]:
            return {"error": "用户关注列表已设置为隐私，无法查看"}
        elif error_code == -404:
            return {"error": f"用户 {user_id} 不存在或已注销"}
        elif error_code == -412:
            # 让装饰器处理 412 重试
            raise ApiException({"code": -412, "message": "Request blocked"})
        elif error_code != 0:
            error_msg = followings_data.get('message', 'Failed to fetch followings')
            return {"error": f"API返回错误（码: {error_code}）: {error_msg}"}
        
        followings_data = followings_data.get('data', {})

    raw_followings = followings_data.get("list", [])
    processed_followings = []
    for f_data in raw_followings:
        processed_following = {
            "mid": f_data.get("mid"),
            "uname": f_data.get("uname"),
            "sign": f_data.get("sign")
        }
        processed_followings.append(processed_following)

    return {"followings": processed_followings, "total": followings_data.get("total", 0)}
