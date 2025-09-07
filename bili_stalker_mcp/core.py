import logging
import time
from typing import Any, Dict, Optional

import requests
import bilibili_api
from bilibili_api import Credential, user, sync, search
from bilibili_api.exceptions import ApiException

from .config import DEFAULT_HEADERS, REQUEST_DELAY, BILIBILI_DYNAMIC_API_URL
from .parsers import parse_dynamics_data

# 配置 bilibili-api 请求设置
bilibili_api.request_settings.set('headers', {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
    'Origin': 'https://www.bilibili.com',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
})
bilibili_api.request_settings.set('timeout', 15.0)

# 重试配置 (来自 config.py)
from .config import REQUEST_DELAY as RETRY_DELAY
MAX_RETRIES = 5
API_RATE_LIMIT_DELAY = 5.0

logger = logging.getLogger(__name__)

def get_credential(sessdata: str, bili_jct: str, buvid3: str) -> Optional[Credential]:
    """创建Bilibili API的凭证对象"""
    if not sessdata:
        logger.error("SESSDATA environment variable is not set.")
        return None
    return Credential(sessdata=sessdata, bili_jct=bili_jct, buvid3=buvid3)

def _build_cookie_string(cred: Credential) -> str:
    """
    构建完整的 Cookie 字符串，用于 requests 回退调用。
    """
    cookie_parts = []
    if getattr(cred, "sessdata", None):
        cookie_parts.append(f"SESSDATA={cred.sessdata}")
    if getattr(cred, "bili_jct", None):
        cookie_parts.append(f"bili_jct={cred.bili_jct}")
    if getattr(cred, "buvid3", None):
        cookie_parts.append(f"buvid3={cred.buvid3}")
    return "; ".join(cookie_parts) if cookie_parts else ""

def get_user_id_by_username(username: str) -> Optional[int]:
    """通过用户名搜索并获取用户ID"""
    if not username:
        return None
    try:
        search_result = sync(search.search_by_type(
            keyword=username,
            search_type=search.SearchObjectType.USER,
            order_type=search.OrderUser.FANS
        ))
        result_list = search_result.get("result") or (search_result.get("data", {}) or {}).get("result")
        if not isinstance(result_list, list) or not result_list:
            logger.warning(f"User '{username}' not found.")
            return None
        
        exact_match = [u for u in result_list if u.get('uname') == username]
        if len(exact_match) == 1:
            return exact_match[0]['mid']
        
        logger.warning(f"No exact match for '{username}', returning the most relevant user.")
        return result_list[0]['mid']
            
    except Exception as e:
        logger.error(f"Error searching for user: {e}")
        return None

def fetch_user_info(user_id: int, cred: Credential) -> Dict[str, Any]:
    """获取并处理B站用户信息"""
    try:
        u = user.User(uid=user_id, credential=cred)
        info = sync(u.get_user_info())
        return {
            "mid": info.get("mid"), "name": info.get("name"), "face": info.get("face"),
            "sign": info.get("sign"), "level": info.get("level"),
            "following": info.get("following"), "follower": info.get("follower")
        }
    except Exception as e:
        logger.error(f"Failed to get user info for UID {user_id}: {e}")
        return {"error": f"Failed to get user info: {e}"}

def fetch_user_videos(user_id: int, limit: int, cred: Credential) -> Dict[str, Any]:
    """获取并处理用户视频列表"""
    try:
        u = user.User(uid=user_id, credential=cred)
        video_list = sync(u.get_videos(ps=limit))
        
        raw_videos = video_list.get("list", {}).get("vlist", [])
        processed_videos = [
            {
                "bvid": v.get("bvid"), "aid": v.get("aid"), "title": v.get("title"),
                "description": v.get("description"), "created": v.get("created"),
                "length": v.get("length"), "pic": v.get("pic"), "play": v.get("play"),
                "favorites": v.get("favorites"), "author": v.get("author"), "mid": v.get("mid"),
                "url": f"https://www.bilibili.com/video/{v.get('bvid')}" if v.get('bvid') else None
            } for v in raw_videos
        ]
        return {"videos": processed_videos, "total": video_list.get("page", {}).get("count", 0)}
    except Exception as e:
        logger.error(f"Failed to get user videos for UID {user_id}: {e}")
        return {"error": f"Failed to get user videos: {e}"}

def _fetch_user_dynamics_fallback(user_id: int, limit: int, cred: Credential, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """使用 polymer web 动态接口的回退方案"""
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Cookie': _build_cookie_string(cred)
    }

    offset = ""
    collected = []

    while len(collected) < limit:
        params = {
            "offset": offset,
            "host_mid": user_id
        }
        retry_count = 0
        resp = None
        while retry_count < MAX_RETRIES:
            try:
                resp = requests.get(BILIBILI_DYNAMIC_API_URL, headers=headers, params=params, timeout=15)
                if resp.status_code == 200:
                    break  # 成功获取响应
                elif resp.status_code == 429:  # 请求过于频繁
                    logger.warning(f"Rate limited (429), retrying in {API_RATE_LIMIT_DELAY} seconds...")
                    time.sleep(API_RATE_LIMIT_DELAY)
                elif resp.status_code == 412:  # 请求被拒绝
                    logger.warning(f"Request blocked (412), body: {resp.text[:200]}")
                    if retry_count < MAX_RETRIES - 1:
                        sleep_time = RETRY_DELAY * (2 ** retry_count)  # 指数退避
                        logger.info(f"Retrying in {sleep_time} seconds due to 412 error...")
                        time.sleep(sleep_time)
                    else:
                        logger.error("Max retries reached for 412 error")
                        break
                else:
                    logger.warning(f"HTTP {resp.status_code}, body: {resp.text[:200]}")
                    break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logger.warning(f"Network error on attempt {retry_count + 1}: {e}")
                if retry_count < MAX_RETRIES - 1:
                    sleep_time = RETRY_DELAY * (2 ** retry_count)
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error("Max retries reached for network error")
                    break

            retry_count += 1

        if not resp or resp.status_code != 200:
            logger.error(f"Failed to get valid response after {MAX_RETRIES} attempts")
            break

        data = resp.json().get("data") or {}
        items = data.get("items") or []

        for it in items:
            if it is None:
                logger.warning("Encountered None item in dynamics, skipping")
                continue

            try:
                dynamic_id = str(it.get("id_str") or it.get("id") or "")
                # 安全获取timestamp，避免NoneType错误
                modules = it.get("modules", {}) or {}
                module_author = modules.get("module_author", {}) or {}
                timestamp = module_author.get("pub_ts") or 0

                # 检查动态类型是否有效
                dynamic_type_num = it.get("type")
                if dynamic_type_num is None:
                    logger.warning("Dynamic item missing type field, skipping")
                    continue

                # 提取文本内容
                modules = it.get("modules", {})
                text_content = ""

                if modules.get("module_dynamic", {}).get("desc", {}).get("text"):
                    text_content = modules["module_dynamic"]["desc"]["text"]

                if not text_content and it.get("type") == "DYNAMIC_TYPE_DRAW":
                    major = modules.get("module_dynamic", {}).get("major", {})
                    if major.get("type") == "MAJOR_TYPE_DRAW":
                        text_content = major.get("draw", {}).get("rich_text", "")

                if not text_content:
                    desc = modules.get("module_dynamic", {}).get("desc", {})
                    text_content = (desc or {}).get("text", "") or (desc or {}).get("rich_desc", {}).get("text", "")

                dynamic_url = it.get("id_str") and f"https://t.bilibili.com/{it.get('id_str')}"

                collected.append({
                    "dynamic_id": dynamic_id,
                    "timestamp": timestamp,
                    "type": dynamic_type_num,
                    "stat": {},
                    "content": {
                        "text": text_content
                    },
                    "url": dynamic_url
                })
            except Exception as parse_error:
                logger.warning(f"Error parsing dynamic item: {parse_error}, skipping this item")
                continue
            if len(collected) >= limit:
                break

        if not data.get("has_more"):
            break
        offset = data.get("offset") or ""
        time.sleep(REQUEST_DELAY)

    # 在fallback函数中也应用动态类型过滤
    if dynamic_type != "ALL":
        type_filters = {
            "VIDEO": ["DYNAMIC_TYPE_AV"],
            "ARTICLE": ["DYNAMIC_TYPE_AV"],
            "ANIME": ["DYNAMIC_TYPE_AV"],
            "DRAW": [2, "DYNAMIC_TYPE_DRAW"],
        }
        if dynamic_type in type_filters:
            collected = [
                d for d in collected
                if d.get("type") in type_filters[dynamic_type]
            ]

    return {"dynamics": collected[:limit], "count": len(collected[:limit])}

def fetch_user_dynamics(user_id: int, limit: int, cred: Credential, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """获取用户动态列表（优先API，失败回退）"""
    try:
        u = user.User(uid=user_id, credential=cred)
        offset = ""
        all_dynamics = []

        while len(all_dynamics) < limit:
            page_data = sync(u.get_dynamics(offset=offset))
            if not page_data or not page_data.get("cards"):
                break

            parsed_page_dynamics = parse_dynamics_data(page_data)

            # 根据动态类型过滤
            if dynamic_type != "ALL":
                type_filters = {
                    "VIDEO": ["DYNAMIC_TYPE_AV"],
                    "ARTICLE": ["DYNAMIC_TYPE_AV"],
                    "ANIME": ["DYNAMIC_TYPE_AV"],
                    "DRAW": [2, "DYNAMIC_TYPE_DRAW"],
                }
                if dynamic_type in type_filters:
                    parsed_page_dynamics = [
                        d for d in parsed_page_dynamics
                        if d.get("type") in type_filters[dynamic_type]
                    ]

            all_dynamics.extend(parsed_page_dynamics)

            if not page_data.get("has_more"):
                break
            offset = page_data.get("offset", "")
            time.sleep(REQUEST_DELAY)

        if all_dynamics:
            return {"dynamics": all_dynamics[:limit], "count": len(all_dynamics[:limit])}
        logger.info("Empty dynamics from bilibili_api, switching to fallback.")
        return _fetch_user_dynamics_fallback(user_id, limit, cred, dynamic_type)
    except ApiException as e:
        logger.warning(f"bilibili_api ApiException in dynamics: {e}, fallback to requests.")
        return _fetch_user_dynamics_fallback(user_id, limit, cred, dynamic_type)
    except Exception as e:
        logger.warning(f"bilibili_api exception in dynamics: {e}, fallback to requests.")
        return _fetch_user_dynamics_fallback(user_id, limit, cred, dynamic_type)
