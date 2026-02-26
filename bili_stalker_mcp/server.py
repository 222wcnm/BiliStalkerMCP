import logging
import time
import uuid
from typing import Annotated, Any, Awaitable, Callable, Dict, Literal, Optional, Tuple

from bilibili_api import Credential
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from . import __version__
from .config import DynamicType
from .core import (
    fetch_article_content,
    fetch_user_articles,
    fetch_user_dynamics,
    fetch_user_followings,
    fetch_user_info,
    fetch_user_videos,
    fetch_video_detail,
    get_credential,
    get_user_id_by_username,
)
from .observability import begin_request, snapshot_metrics


DynamicTypeLiteral = Literal["ALL", "ALL_RAW", "VIDEO", "ARTICLE", "DRAW", "TEXT"]
SubtitleModeLiteral = Literal["minimal", "smart", "full"]

MAX_PAGE = 1000
MAX_VIDEO_LIMIT = 30
MAX_DYNAMIC_LIMIT = 30
MAX_ARTICLE_LIMIT = 30
MAX_FOLLOWING_LIMIT = 50


def _get_credential_from_context(_ctx: Context) -> Credential:
    """Get credential from environment or raise protocol-level tool error."""
    cred = get_credential()
    if cred is None:
        raise ToolError("Missing SESSDATA. Please provide SESSDATA in environment variables.")
    return cred


def _parse_user_identifier(user_id_or_username: str) -> Tuple[Optional[int], Optional[str]]:
    """Parse a user identifier string into (user_id, username)."""
    try:
        return int(user_id_or_username), None
    except ValueError:
        return None, user_id_or_username


def create_server() -> FastMCP:
    """Create and configure the BiliStalkerMCP server."""
    logger = logging.getLogger(__name__)
    mcp = FastMCP("BiliStalkerMCP", version=__version__)

    async def _resolve_user_id(user_id: int | None, username: str | None) -> int:
        if user_id is not None:
            return user_id

        if username:
            resolved = await get_user_id_by_username(username)
            if resolved is not None:
                return resolved

        raise ToolError(f"User '{username or user_id}' was not found.")

    async def _run_tool(
        tool_name: str,
        runner: Callable[[], Awaitable[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        request_id = uuid.uuid4().hex
        begin_request(request_id)
        started = time.perf_counter()

        try:
            result = await runner()
            total_duration_ms = round((time.perf_counter() - started) * 1000, 3)
            metrics = snapshot_metrics()
            logger.info(
                "tool_call_succeeded",
                extra={
                    "event": "tool_call_succeeded",
                    "tool": tool_name,
                    "request_id": request_id,
                    "duration_ms": total_duration_ms,
                    "upstream_duration_ms": metrics["upstream_duration_ms"],
                    "retry_count": metrics["retry_count"],
                    "cache": metrics["cache"],
                },
            )
            return result
        except Exception as exc:
            total_duration_ms = round((time.perf_counter() - started) * 1000, 3)
            metrics = snapshot_metrics()
            logger.error(
                "tool_call_failed",
                extra={
                    "event": "tool_call_failed",
                    "tool": tool_name,
                    "request_id": request_id,
                    "duration_ms": total_duration_ms,
                    "upstream_duration_ms": metrics["upstream_duration_ms"],
                    "retry_count": metrics["retry_count"],
                    "cache": metrics["cache"],
                    "error": str(exc),
                },
            )
            raise

    @mcp.prompt()
    def track_user_updates() -> str:
        """Generate a workflow prompt for tracking a Bilibili user."""
        return (
            "Track a target Bilibili user in this order: \n"
            "1) get_user_info \n"
            "2) get_user_videos \n"
            "3) get_video_detail (for videos that need full context) \n"
            "4) get_user_dynamics \n"
            "5) get_user_articles \n"
            "6) get_article_content (for articles that need full context) \n"
            "Then summarize by publish time and highlight major changes."
        )

    @mcp.prompt()
    def analyze_user_activity() -> str:
        """Generate a workflow prompt for analyzing a Bilibili user."""
        return (
            "Analyze one Bilibili user's content behavior: \n"
            "1) Collect profile + lightweight lists (videos, dynamics, articles). \n"
            "2) Fetch details only for high-value items (video/article detail tools). \n"
            "3) Measure cadence and content-type mix. \n"
            "4) Summarize top themes and recent shifts."
        )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )
    async def get_user_info(
        ctx: Context,
        user_id_or_username: Annotated[
            str,
            Field(
                min_length=1,
                description="Bilibili user id (numeric) or username.",
            ),
        ],
    ) -> Dict[str, Any]:
        """Get profile information for a Bilibili user."""

        async def _runner() -> Dict[str, Any]:
            cred = _get_credential_from_context(ctx)
            user_id, username = _parse_user_identifier(user_id_or_username)
            target_uid = await _resolve_user_id(user_id, username)
            return await fetch_user_info(target_uid, cred)

        try:
            return await _run_tool("get_user_info", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("get_user_info failed")
            raise ToolError(f"Failed to fetch user info: {exc}")

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )
    async def get_user_videos(
        ctx: Context,
        user_id_or_username: Annotated[
            str,
            Field(
                min_length=1,
                description="Bilibili user id (numeric) or username.",
            ),
        ],
        page: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_PAGE,
                description="Page number starting from 1.",
            ),
        ] = 1,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_VIDEO_LIMIT,
                description=f"Items per page, 1-{MAX_VIDEO_LIMIT}.",
            ),
        ] = 10,
    ) -> Dict[str, Any]:
        """Get lightweight video list for a user."""

        async def _runner() -> Dict[str, Any]:
            cred = _get_credential_from_context(ctx)
            user_id, username = _parse_user_identifier(user_id_or_username)
            target_uid = await _resolve_user_id(user_id, username)
            return await fetch_user_videos(target_uid, page, limit, cred)

        try:
            return await _run_tool("get_user_videos", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("get_user_videos failed")
            raise ToolError(f"Failed to fetch user videos: {exc}")

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )
    async def get_video_detail(
        ctx: Context,
        bvid: Annotated[
            str,
            Field(
                min_length=3,
                description="Video BVID, e.g. BV1xx411c7mD.",
            ),
        ],
        fetch_subtitles: Annotated[
            bool,
            Field(description="Whether to fetch and aggregate subtitle tracks."),
        ] = False,
        subtitle_mode: Annotated[
            SubtitleModeLiteral,
            Field(
                description=(
                    "Subtitle fetch mode when fetch_subtitles=true: "
                    "minimal (no subtitle API), smart (single best track text), "
                    "full (all track texts)."
                )
            ),
        ] = "smart",
        subtitle_lang: Annotated[
            str,
            Field(
                description=(
                    "Requested subtitle language code (e.g. zh-CN, en-US). "
                    "Use auto for built-in priority fallback."
                )
            ),
        ] = "auto",
        subtitle_max_chars: Annotated[
            int,
            Field(
                ge=1,
                le=200000,
                description="Maximum subtitle text characters returned in this response.",
            ),
        ] = 12000,
    ) -> Dict[str, Any]:
        """Get full video detail and optional subtitles."""

        async def _runner() -> Dict[str, Any]:
            cred = _get_credential_from_context(ctx)
            return await fetch_video_detail(
                bvid=bvid,
                fetch_subtitles=fetch_subtitles,
                subtitle_mode=subtitle_mode,
                subtitle_lang=subtitle_lang,
                subtitle_max_chars=subtitle_max_chars,
                cred=cred,
            )

        try:
            return await _run_tool("get_video_detail", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("get_video_detail failed")
            raise ToolError(f"Failed to fetch video detail: {exc}")

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )
    async def get_user_dynamics(
        ctx: Context,
        user_id_or_username: Annotated[
            str,
            Field(
                min_length=1,
                description="Bilibili user id (numeric) or username.",
            ),
        ],
        cursor: Annotated[
            str | None,
            Field(
                description="Opaque cursor for cursor-based pagination.",
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_DYNAMIC_LIMIT,
                description=f"Items to fetch, 1-{MAX_DYNAMIC_LIMIT}.",
            ),
        ] = 10,
        dynamic_type: Annotated[
            DynamicTypeLiteral,
            Field(
                description=(
                    "Allowed values: "
                    f"{DynamicType.ALL}, {DynamicType.ALL_RAW}, {DynamicType.VIDEO}, "
                    f"{DynamicType.ARTICLE}, {DynamicType.DRAW}, {DynamicType.TEXT}."
                )
            ),
        ] = DynamicType.ALL,
    ) -> Dict[str, Any]:
        """Get user dynamics with type filtering and cursor pagination."""

        async def _runner() -> Dict[str, Any]:
            cred = _get_credential_from_context(ctx)
            user_id, username = _parse_user_identifier(user_id_or_username)
            target_uid = await _resolve_user_id(user_id, username)
            return await fetch_user_dynamics(
                user_id=target_uid,
                limit=limit,
                cred=cred,
                dynamic_type=dynamic_type,
                cursor=cursor,
            )

        try:
            return await _run_tool("get_user_dynamics", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("get_user_dynamics failed")
            raise ToolError(f"Failed to fetch user dynamics: {exc}")

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )
    async def get_user_articles(
        ctx: Context,
        user_id_or_username: Annotated[
            str,
            Field(
                min_length=1,
                description="Bilibili user id (numeric) or username.",
            ),
        ],
        page: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_PAGE,
                description="Page number starting from 1.",
            ),
        ] = 1,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_ARTICLE_LIMIT,
                description=f"Items per page, 1-{MAX_ARTICLE_LIMIT}.",
            ),
        ] = 10,
    ) -> Dict[str, Any]:
        """Get lightweight article list for a user."""

        async def _runner() -> Dict[str, Any]:
            cred = _get_credential_from_context(ctx)
            user_id, username = _parse_user_identifier(user_id_or_username)
            target_uid = await _resolve_user_id(user_id, username)
            return await fetch_user_articles(target_uid, page, limit, cred)

        try:
            return await _run_tool("get_user_articles", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("get_user_articles failed")
            raise ToolError(f"Failed to fetch user articles: {exc}")

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )
    async def get_article_content(
        ctx: Context,
        article_id: Annotated[
            int,
            Field(
                ge=1,
                description="Article CV id.",
            ),
        ],
    ) -> Dict[str, Any]:
        """Get full article markdown content."""

        async def _runner() -> Dict[str, Any]:
            cred = _get_credential_from_context(ctx)
            return await fetch_article_content(article_id=article_id, cred=cred)

        try:
            return await _run_tool("get_article_content", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("get_article_content failed")
            raise ToolError(f"Failed to fetch article content: {exc}")

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )
    async def get_user_followings(
        ctx: Context,
        user_id_or_username: Annotated[
            str,
            Field(
                min_length=1,
                description="Bilibili user id (numeric) or username.",
            ),
        ],
        page: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_PAGE,
                description="Page number starting from 1.",
            ),
        ] = 1,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_FOLLOWING_LIMIT,
                description=f"Items per page, 1-{MAX_FOLLOWING_LIMIT}.",
            ),
        ] = 20,
    ) -> Dict[str, Any]:
        """Get user followings."""

        async def _runner() -> Dict[str, Any]:
            cred = _get_credential_from_context(ctx)
            user_id, username = _parse_user_identifier(user_id_or_username)
            target_uid = await _resolve_user_id(user_id, username)
            return await fetch_user_followings(target_uid, page, limit, cred)

        try:
            return await _run_tool("get_user_followings", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("get_user_followings failed")
            raise ToolError(f"Failed to fetch user followings: {exc}")

    return mcp
