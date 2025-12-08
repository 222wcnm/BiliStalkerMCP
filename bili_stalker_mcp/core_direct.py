#!/usr/bin/env python3
"""Low-level Bilibili API implementation using raw HTTP requests."""

import os
import logging
import hashlib
import random
import time
from typing import Any, Dict, Optional, Tuple

import httpx
import asyncio

from .config import DEFAULT_HEADERS, REQUEST_TIMEOUT, CONNECT_TIMEOUT, READ_TIMEOUT

logger = logging.getLogger(__name__)

class DirectBilibiliClient:
    """Direct HTTP client for Bilibili API, avoiding high-level wrappers."""

    def __init__(self, sessdata: str, bili_jct: Optional[str] = None, buvid3: Optional[str] = None):
        self.sessdata = sessdata
        self.bili_jct = bili_jct or ""
        self.buvid3 = buvid3 or self._generate_buvid3()
        self.base_headers = DEFAULT_HEADERS.copy()

        # 扩展User-Agent列表，增加更多真实浏览器标识和版本变化
        user_agents = [
            # Chrome variants with different versions
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            # macOS variants
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            # Linux variants
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
            # Firefox variants
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
            # Edge variants
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
        ]
        # 使用更随机的方式选择User-Agent
        self.base_headers['User-Agent'] = random.choice(user_agents)

        # 添加更多真实浏览器请求头
        self.base_headers['X-Timezone'] = 'Asia/Shanghai'
        self.base_headers['Accept-Encoding'] = 'gzip, deflate, br'
        self.base_headers['Connection'] = 'keep-alive'
        self.base_headers['DNT'] = '1'

    def _generate_buvid3(self) -> str:
        """Generate a pseudo-buvid3 for device fingerprinting."""
        seed = str(random.random()) + str(time.time())
        return hashlib.md5(seed.encode()).hexdigest()[:32].upper()

    def _get_cookies(self) -> str:
        """Build cookie string for requests."""
        cookies = []
        if self.sessdata:
            cookies.append(f"SESSDATA={self.sessdata}")
        if self.bili_jct:
            cookies.append(f"bili_jct={self.bili_jct}")
        if self.buvid3:
            cookies.append(f"buvid3={self.buvid3}")
        return "; ".join(cookies)

    async def _make_request(self, url: str, params: Optional[Dict[str, Any]] = None,
                          method: str = "GET") -> Tuple[bool, Dict[str, Any]]:
        """Make HTTP request with comprehensive error handling."""
        max_retries = 5  # 增加重试次数
        for attempt in range(max_retries):
            try:
                headers = self.base_headers.copy()
                headers['Cookie'] = self._get_cookies()
                headers['X-Requested-With'] = 'XMLHttpRequest'  # Mark as AJAX request

                # 每次请求都重新随机User-Agent
                user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
                ]
                headers['User-Agent'] = random.choice(user_agents)

                # 添加更真实的请求头
                headers['Sec-Fetch-Dest'] = 'empty'
                headers['Sec-Fetch-Mode'] = 'cors'
                headers['Sec-Fetch-Site'] = 'same-origin'
                headers['sec-gpc'] = '1'

                # 增加请求间随机延迟，避免模式化请求
                if attempt > 0:
                    delay = random.uniform(2, 8)  # 重试时增加更长的随机延迟
                    await asyncio.sleep(delay)

                async with httpx.AsyncClient(timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT)) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, params=params, headers=headers)
                    elif method.upper() == "POST":
                        response = await client.post(url, params=params, headers=headers)
                    else:
                        return False, {"error": f"Unsupported method: {method}"}

                    response.raise_for_status()
                    data = response.json()

                    # Check for Bilibili-specific errors
                    if data.get('code') != 0:
                        error_code = data.get('code')
                        error_msg = data.get('message', 'Unknown error')

                        # Handle specific error codes
                        if error_code == -412:
                            if attempt < max_retries - 1:
                                # 指数退避 + 随机化 + 切换身份标识
                                wait_time = (2 ** attempt) + random.uniform(3, 10)
                                logger.warning(f"Request blocked by anti-crawler system (412). Retrying in {wait_time:.2f} seconds (attempt {attempt + 1}/{max_retries})...")
                                await asyncio.sleep(wait_time)

                                # 重新生成buvid3来切换设备指纹
                                self.buvid3 = self._generate_buvid3()
                                continue
                            else:
                                return False, {
                                    "error": "Request blocked by anti-crawler system after all retries. "
                                    "This may indicate IP-based restrictions or invalid credentials. "
                                    "Try using a different network or fresh cookies."
                                }
                        elif error_code == -509:
                            return False, {"error": "Request rate limited (509)"}
                        elif error_code == -404:
                            return False, {"error": "User not found (404)"}
                        else:
                            return False, {"error": f"Bilibili API error ({error_code}): {error_msg}"}

                    return True, data.get('data', {})

            except httpx.RequestError as e:
                logger.error(f"HTTP request failed: {e}")
                if attempt < max_retries - 1:
                    # 增加延迟并重试
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Request failed. Retrying in {wait_time:.2f} seconds...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    return False, {"error": f"Network error: {str(e)}"}
            except Exception as e:
                logger.error(f"Unexpected error in API request: {e}")
                if attempt < max_retries - 1:
                    # 增加延迟并重试
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Request failed. Retrying in {wait_time:.2f} seconds...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    return False, {"error": f"Request failed: {str(e)}"}
        
        # 如果所有重试都失败了，返回错误
        return False, {"error": "All retry attempts failed"}

    async def get_user_info(self, uid: int) -> Dict[str, Any]:
        """Get user information using low-level API."""
        url = "https://api.bilibili.com/x/space/acc/info"
        success, data = await self._make_request(url, {"mid": uid})
        if not success:
            return data  # Return error dict

        return {
            "mid": data.get("mid"),
            "name": data.get("name"),
            "face": data.get("face"),
            "sign": data.get("sign"),
            "level": data.get("level"),
            "birthday": data.get("birthday", ""),
            "sex": data.get("sex", "")
        }

    async def get_user_videos(self, uid: int, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """Get user videos using low-level API."""
        url = "https://api.bilibili.com/x/space/arc/search"
        params = {
            "mid": uid,
            "pn": page,
            "ps": limit,
            "tid": 0,
            "keyword": "",
            "order": "pubdate"
        }

        success, data = await self._make_request(url, params)
        if not success:
            return data

        videos = []
        for item in data.get("list", {}).get("vlist", []):
            videos.append({
                "mid": item.get("mid"),
                "bvid": item.get("bvid"),
                "aid": item.get("aid"),
                "title": item.get("title"),
                "description": item.get("description", ""),
                "created": item.get("created"),
                "length": item.get("length"),
                "play": item.get("play"),
                "comment": item.get("comment"),
                "pic": item.get("pic", "")
            })

        return {"videos": videos}

    async def get_user_relations(self, uid: int) -> Dict[str, Any]:
        """Get user relationship stats."""
        url = "https://api.bilibili.com/x/relation/stat"
        success, data = await self._make_request(url, {"vmid": uid})
        if not success:
            return data

        return {
            "following": data.get("following"),
            "follower": data.get("follower")
        }


# Global client instance (initialized in get_direct_client())
_direct_client: Optional[DirectBilibiliClient] = None

async def get_direct_client() -> Optional[DirectBilibiliClient]:
    """Get or create the direct Bilibili client."""
    global _direct_client

    if _direct_client:
        return _direct_client

    # Try to get credentials like the original implementation
    try:
        from .core import get_credential
        cred = get_credential()
        if cred:
            _direct_client = DirectBilibiliClient(
                sessdata=cred.sessdata or "",
                bili_jct=cred.bili_jct or "",
                buvid3=getattr(cred, 'buvid3', None) or ""
            )
            logger.info("Successfully created direct Bilibili client with credentials")
            return _direct_client
        else:
            # 尝试从环境变量或文件直接获取凭证
            sessdata = os.environ.get("SESSDATA")
            bili_jct = os.environ.get("BILI_JCT")
            buvid3 = os.environ.get("BUVID3")
            
            # 如果环境变量中没有凭证，则尝试从文件中读取
            if not sessdata:
                try:
                    cookie_file_path = os.path.join(os.path.dirname(__file__), "..", "BILI_COOKIE.txt")
                    if os.path.exists(cookie_file_path):
                        with open(cookie_file_path, "r", encoding="utf-8") as f:
                            cookie_content = f.read().strip()
                            
                        # 解析cookie字符串
                        cookies = {}
                        for cookie in cookie_content.split(";"):
                            if "=" in cookie:
                                key, value = cookie.strip().split("=", 1)
                                cookies[key] = value
                        
                        sessdata = cookies.get("SESSDATA")
                        bili_jct = cookies.get("bili_jct")
                        buvid3 = cookies.get("buvid3")
                        
                        if sessdata:
                            logger.info("Successfully loaded credentials from BILI_COOKIE.txt for direct client")
                except Exception as e:
                    logger.warning(f"Failed to load credentials from BILI_COOKIE.txt for direct client: {e}")
            
            if sessdata:
                _direct_client = DirectBilibiliClient(
                    sessdata=sessdata or "",
                    bili_jct=bili_jct or "",
                    buvid3=buvid3 or ""
                )
                logger.info("Successfully created direct Bilibili client with file/env credentials")
                return _direct_client
    except Exception as e:
        logger.warning(f"Failed to create direct client: {e}")

    logger.error("Failed to create direct Bilibili client - no valid credentials found")
    return None
