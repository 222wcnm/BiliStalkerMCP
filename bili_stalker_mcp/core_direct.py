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

        # Rotate User-Agent based on timestamp to avoid detection
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        ]
        timestamp = int(time.time())
        self.base_headers['User-Agent'] = user_agents[timestamp % len(user_agents)]

        # Add timezone header for realism
        self.base_headers['X-Timezone'] = 'Asia/Shanghai'

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
                          method: str = "GET") -> Tuple[bool, dict]:
        """Make HTTP request with comprehensive error handling."""
        try:
            headers = self.base_headers.copy()
            headers['Cookie'] = self._get_cookies()
            headers['X-Requested-With'] = 'XMLHttpRequest'  # Mark as AJAX request

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
                        return False, {
                            "error": "Request blocked by anti-crawler system (412). "
                            "Try updating cookies or use different User-Agent."
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
            return False, {"error": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error in API request: {e}")
            return False, {"error": f"Request failed: {str(e)}"}

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
            return _direct_client
    except Exception as e:
        logger.warning(f"Failed to create direct client: {e}")

    return None
