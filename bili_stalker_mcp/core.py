import logging
import time
import os
from datetime import datetime, timezone
import random
from typing import Any, Dict, Optional

import requests
import bilibili_api
from bilibili_api import Credential, user, sync, search
from bilibili_api.exceptions import ApiException

from .config import (
    DEFAULT_HEADERS, REQUEST_DELAY, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX,
    BILIBILI_DYNAMIC_API_URL, PROXY_CONFIG, REQUEST_TIMEOUT,
    CONNECT_TIMEOUT, READ_TIMEOUT
)
from .parsers import parse_dynamics_data

# 配置 bilibili-api 请求设置
bilibili_api.request_settings.set('headers', DEFAULT_HEADERS)
bilibili_api.request_settings.set('timeout', REQUEST_TIMEOUT)

# 配置代理设置（如果环境变量中有设置）
proxy_config = {}
if os.environ.get('HTTP_PROXY'):
    proxy_config['http'] = os.environ.get('HTTP_PROXY')
if os.environ.get('HTTPS_PROXY'):
    proxy_config['https'] = os.environ.get('HTTPS_PROXY')
if proxy_config:
    bilibili_api.request_settings.set('proxies', proxy_config)

# 重试配置 (来自 config.py)
from .config import REQUEST_DELAY as RETRY_DELAY
MAX_RETRIES = 5
API_RATE_LIMIT_DELAY = 5.0

logger = logging.getLogger(__name__)

def _detect_network_environment() -> Dict[str, Any]:
    """检测网络环境，返回环境信息和建议配置"""
    env_info = {
        "is_cloud_env": False,
        "has_proxy": False,
        "suggested_config": {}
    }
    
    # 检测是否在云环境中运行
    cloud_indicators = [
        "MODELSCOPE" in os.environ,
        "CLOUD" in os.environ.get("HOSTNAME", "").upper(),
        "KUBERNETES" in os.environ,
        "DOCKER" in os.environ.get("HOSTNAME", "").upper()
    ]
    
    if any(cloud_indicators):
        env_info["is_cloud_env"] = True
        env_info["suggested_config"] = {
            "use_proxy": True,
            "increase_timeout": True,
            "reduce_request_frequency": True
        }
    
    # 检测代理配置
    if os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY'):
        env_info["has_proxy"] = True
    
    return env_info

def get_credential(sessdata: str, bili_jct: str, buvid3: str) -> Optional[Credential]:
    """创建Bilibili API的凭证对象"""
    if not sessdata:
        logger.error("SESSDATA environment variable is not set or empty. Please set the SESSDATA environment variable with your Bilibili cookies.")
        logger.info("You can get SESSDATA by logging into bilibili.com and inspecting cookies in browser developer tools.")
        return None

    logger.info("Creating Bilibili credential with provided SESSDATA")
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
        # 验证返回的数据结构
        if not info or 'mid' not in info:
            raise ValueError("User info response is invalid")
        return {
            "mid": info.get("mid"), "name": info.get("name"), "face": info.get("face"),
            "sign": info.get("sign"), "level": info.get("level"),
            "following": info.get("following"), "follower": info.get("follower")
        }
    except ApiException as e:
        logger.error(f"API error when fetching user info for UID {user_id}: {e}")
        if e.code == -412:
            return {"error": "请求被B站服务器拒绝 (412)，可能是因为SESSDATA等凭证失效或网络环境被限制。"}
        return {"error": f"获取用户信息时B站API错误: {e.msg} (代码: {e.code})"}
    except Exception as e:
        logger.error(f"Failed to get user info for UID {user_id}: {e}")
        return {"error": f"获取用户信息失败: {e}"}

def fetch_user_videos(user_id: int, limit: int, cred: Credential) -> Dict[str, Any]:
    """获取并处理用户视频列表"""
    try:
        u = user.User(uid=user_id, credential=cred)
        video_list = sync(u.get_videos(ps=limit))
        
        raw_videos = video_list.get("list", {}).get("vlist", [])
        processed_videos = []
        for v in raw_videos:
            created_timestamp = v.get("created")
            if created_timestamp:
                # Bilibili API返回的是东八区时间戳，直接转换为ISO 8601字符串
                publish_time = datetime.fromtimestamp(created_timestamp, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            else:
                publish_time = None
            
            processed_videos.append({
                "bvid": v.get("bvid"), "aid": v.get("aid"), "title": v.get("title"),
                "description": v.get("description"), "created": publish_time,
                "length": v.get("length"), "pic": v.get("pic"), "play": v.get("play"),
                "favorites": v.get("favorites"), "author": v.get("author"), "mid": v.get("mid"),
                "url": f"https://www.bilibili.com/video/{v.get('bvid')}" if v.get('bvid') else None
            })
        return {"videos": processed_videos, "total": video_list.get("page", {}).get("count", 0)}
    except ApiException as e:
        logger.error(f"API error when fetching user videos for UID {user_id}: {e}")
        if e.code == -412:
            return {"error": "请求被B站服务器拒绝 (412)，可能是因为SESSDATA等凭证失效或网络环境被限制。"}
        return {"error": f"获取视频列表时B站API错误: {e.msg} (代码: {e.code})"}
    except Exception as e:
        logger.error(f"Failed to get user videos for UID {user_id}: {e}")
        return {"error": f"获取用户视频失败: {e}"}

def fetch_user_dynamics(user_id: int, limit: int, cred: Credential, dynamic_type: str = "ALL") -> Dict[str, Any]:
    """
    获取用户动态列表。
    由于bilibili-api的动态API已不稳定，此函数直接使用requests调用Web API。
    """
    headers = DEFAULT_HEADERS.copy()
    headers['Cookie'] = _build_cookie_string(cred)
    
    proxies = PROXY_CONFIG.copy()
    if os.environ.get('HTTP_PROXY'):
        proxies['http'] = os.environ.get('HTTP_PROXY')
    if os.environ.get('HTTPS_PROXY'):
        proxies['https'] = os.environ.get('HTTPS_PROXY')

    offset = ""
    collected = []

    while len(collected) < limit:
        params = {"offset": offset, "host_mid": user_id}

        try:
            resp = requests.get(
                BILIBILI_DYNAMIC_API_URL,
                headers=headers,
                params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                proxies=proxies if any(proxies.values()) else None
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                items = data.get("items", [])

                for item in items:
                    if item is None: continue
                    parsed_item = parse_dynamics_data(item)
                    if parsed_item:
                        collected.append(parsed_item)
                    if len(collected) >= limit: break

                if not data.get("has_more") or len(collected) >= limit:
                    break
                offset = data.get("offset", "")

                # 随机延迟：根据数据量动态调整延迟时间
                if len(collected) > 0 and len(data.get("items", [])) > 0:
                    # 当成功获取数据时，使用较长的随机延迟
                    delay = random.uniform(REQUEST_DELAY_MIN * 1.5, REQUEST_DELAY_MAX * 2.0)
                    logger.info(f"Successfully fetched {len(data.get('items', []))} items, waiting {delay:.2f} seconds...")
                else:
                    # 当获取空数据时，使用较短的固定延迟
                    delay = REQUEST_DELAY_MIN
                    logger.info(f"Empty response, waiting {delay:.2f} seconds...")

                time.sleep(delay)
            elif resp.status_code == 412:
                logger.error("Request blocked by Bilibili (412). Check credentials or network.")
                return {"error": "请求被B站服务器拒绝 (412)，请检查SESSDATA等凭证是否有效或已过期。"}
            else:
                logger.error(f"HTTP Error {resp.status_code}: {resp.text[:200]}")
                return {"error": f"获取动态时遇到HTTP错误，状态码：{resp.status_code}"}

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error when fetching dynamics: {e}")
            return {"error": f"网络请求错误: {e}"}

    # 类型过滤
    if dynamic_type != "ALL":
        type_map = {
            "VIDEO": "DYNAMIC_TYPE_AV",
            "ARTICLE": "DYNAMIC_TYPE_ARTICLE",
            "DRAW": "DYNAMIC_TYPE_DRAW",
        }
        target_type = type_map.get(dynamic_type)
        if target_type:
            collected = [d for d in collected if d.get("type") == target_type]

    return {"dynamics": collected[:limit], "count": len(collected)}
