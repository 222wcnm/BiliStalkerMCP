#!/usr/bin/env python3
"""Server using direct HTTP implementation bypassing bilibili-api library."""

import logging
from typing import Any, Dict

from fastmcp import FastMCP, Context

from .core_direct import get_direct_client

logger = logging.getLogger(__name__)

def create_server_direct():
    """Create server using direct HTTP implementation."""
    logger = logging.getLogger(__name__)
    mcp = FastMCP("BiliStalkerDirectMCP")

    async def get_user_info(ctx: Context, user_id_or_username: str) -> Dict[str, Any]:
        """获取指定哔哩哔哩用户的详细信息 (Direct Implementation)

        Args:
            user_id_or_username: 用户ID（数字）或用户名
        """
        try:
            # Get credentials (this will use Smithery or env vars)
            client = await get_direct_client()
            if not client:
                raise ValueError("No authentication credentials available")

            # Parse user input
            try:
                user_id = int(user_id_or_username)
            except ValueError:
                # TODO: Implement username to ID resolution with direct HTTP
                raise ValueError("Username resolution not implemented in direct mode yet")

            # Get user info
            info = await client.get_user_info(user_id)

            # Check if error was returned
            if "error" in info:
                raise ValueError(info["error"])

            # Get relation stats if user info succeeded
            relations = await client.get_user_relations(user_id)
            if "error" not in relations:
                info["following"] = relations.get("following")
                info["follower"] = relations.get("follower")

            return info

        except ValueError as e:
            raise e  # FastMCP will handle this properly
        except Exception as e:
            logger.error(f"Error in get_user_info (direct): {e}")
            raise ValueError(f"获取用户失败: {str(e)}")

    async def get_user_video_updates(ctx: Context, user_id_or_username: str, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """获取用户的最新视频更新列表 (Direct Implementation)

        Args:
            user_id_or_username: 用户ID（数字）或用户名
            page: 页码（从1开始），默认为1
            limit: 每页视频数量（最大30），默认为10
        """
        try:
            client = await get_direct_client()
            if not client:
                raise ValueError("No authentication credentials available")

            # Parse user input
            try:
                user_id = int(user_id_or_username)
            except ValueError:
                # TODO: Implement username to ID resolution
                raise ValueError("Username resolution not implemented in direct mode yet")

            videos = await client.get_user_videos(user_id, page, limit)
            if "error" in videos:
                raise ValueError(videos["error"])

            return videos

        except ValueError as e:
            raise e
        except Exception as e:
            logger.error(f"Error in get_user_video_updates (direct): {e}")
            raise ValueError(f"获取视频失败: {str(e)}")

    # Register tools
    mcp.tool()(get_user_info)
    mcp.tool()(get_user_video_updates)

    return mcp
