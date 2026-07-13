import logging
import time
import uuid
from typing import (
    Annotated,
    Any,
    Awaitable,
    Callable,
    Dict,
    Literal,
    Optional,
    Tuple,
)

from bilibili_api import Credential
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from . import __version__
from .config import DynamicType
from .cookie_refresh import (
    CookieRefreshConfigError,
    CookieRefreshError,
    load_refreshing_credential,
    validate_cookie_refresh_runtime,
)
from .core import (
    fetch_article_content,
    fetch_content_comment_replies,
    fetch_content_comments,
    fetch_user_articles,
    fetch_user_dynamics,
    fetch_user_followings,
    fetch_user_info,
    fetch_user_videos,
    fetch_video_detail,
    get_credential,
    get_user_id_by_username,
)
from .credentials import cookie_refresh_enabled
from .errors import RiskControlError, public_error_json
from .observability import begin_request, snapshot_metrics
from .utils import extract_bvid

DynamicTypeLiteral = Literal[
    "ALL", "ALL_RAW", "VIDEO", "ARTICLE", "DRAW", "TEXT", "REVIEW"
]
SubtitleModeLiteral = Literal["minimal", "smart", "full"]
CommentContentTypeLiteral = Literal["video", "article", "dynamic"]

MAX_PAGE = 1000
MAX_VIDEO_LIMIT = 30
MAX_DYNAMIC_LIMIT = 30
MAX_ARTICLE_LIMIT = 30
MAX_FOLLOWING_LIMIT = 50


async def _get_credential_from_context(_ctx: Context) -> Credential:
    """Get credential from environment or raise protocol-level tool error."""
    try:
        if cookie_refresh_enabled():
            return await load_refreshing_credential()

        cred = get_credential()
        if cred is None:
            raise ToolError(
                "Missing SESSDATA. Set SESSDATA or provide BILI_COOKIE_FILE."
            )
        return cred
    except ToolError:
        raise
    except CookieRefreshConfigError as exc:
        raise ToolError(str(exc)) from None
    except RiskControlError as exc:
        tool_error = ToolError(public_error_json(exc))
        setattr(tool_error, "code", exc.code)
        setattr(tool_error, "retry_after", exc.retry_after)
        raise tool_error from None
    except CookieRefreshError as exc:
        raise ToolError(public_error_json(exc)) from None
    except Exception as exc:  # pragma: no cover - defensive safety boundary
        raise ToolError(public_error_json(exc)) from None


def _parse_user_identifier(
    user_id_or_username: str,
) -> Tuple[Optional[int], Optional[str]]:
    """Parse a user identifier string into (user_id, username)."""
    try:
        return int(user_id_or_username), None
    except ValueError:
        return None, user_id_or_username


async def _normalize_comment_content_id(
    content_type: CommentContentTypeLiteral,
    content_id: str,
) -> str:
    if content_type == "video":
        return await extract_bvid(content_id)

    stripped = content_id.strip()
    if not stripped.isdigit() or int(stripped) < 1:
        raise ToolError(
            f"{content_type} content_id must be a positive numeric string, "
            f"got: {content_id!r}"
        )
    return stripped


def create_server() -> FastMCP:
    """Create and configure the BiliStalkerMCP server."""
    validate_cookie_refresh_runtime()
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
                    "upstream_call_count": metrics["upstream_call_count"],
                    "retry_count": metrics["retry_count"],
                    "throttle_sleep_ms": metrics["throttle_sleep_ms"],
                    "lazy_pause_count": metrics["lazy_pause_count"],
                    "lazy_pause_ms": metrics["lazy_pause_ms"],
                    "upstream_block_count": metrics["upstream_block_count"],
                    "upstream_rate_limit_count": metrics["upstream_rate_limit_count"],
                    "cache": metrics["cache"],
                },
            )
            return result
        except Exception as exc:
            total_duration_ms = round((time.perf_counter() - started) * 1000, 3)
            metrics = snapshot_metrics()
            public_error = public_error_json(exc, request_id=request_id)
            logger.error(
                "tool_call_failed",
                extra={
                    "event": "tool_call_failed",
                    "tool": tool_name,
                    "request_id": request_id,
                    "duration_ms": total_duration_ms,
                    "upstream_duration_ms": metrics["upstream_duration_ms"],
                    "upstream_call_count": metrics["upstream_call_count"],
                    "retry_count": metrics["retry_count"],
                    "throttle_sleep_ms": metrics["throttle_sleep_ms"],
                    "lazy_pause_count": metrics["lazy_pause_count"],
                    "lazy_pause_ms": metrics["lazy_pause_ms"],
                    "upstream_block_count": metrics["upstream_block_count"],
                    "upstream_rate_limit_count": metrics["upstream_rate_limit_count"],
                    "cache": metrics["cache"],
                    "error": public_error,
                },
            )
            if isinstance(exc, ToolError):
                raise
            raise ToolError(public_error) from exc

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
            cred = await _get_credential_from_context(ctx)
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
            cred = await _get_credential_from_context(ctx)
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
    async def search_user_videos(
        ctx: Context,
        user_id_or_username: Annotated[
            str,
            Field(
                min_length=1,
                description="Bilibili user id (numeric) or username.",
            ),
        ],
        keyword: Annotated[
            str,
            Field(
                min_length=1,
                description="Keyword used to search in target user's video list.",
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
        """Search a user's videos by keyword."""

        async def _runner() -> Dict[str, Any]:
            cred = await _get_credential_from_context(ctx)
            user_id, username = _parse_user_identifier(user_id_or_username)
            target_uid = await _resolve_user_id(user_id, username)
            return await fetch_user_videos(
                target_uid,
                page,
                limit,
                cred,
                keyword=keyword,
            )

        try:
            return await _run_tool("search_user_videos", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("search_user_videos failed")
            raise ToolError(f"Failed to search user videos: {exc}")

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
                description="Video BVID (e.g. BV1xx411c7mD), AV number (e.g. av170001), or a Bilibili video URL.",
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
            cred = await _get_credential_from_context(ctx)
            resolved_bvid = await extract_bvid(bvid)
            return await fetch_video_detail(
                bvid=resolved_bvid,
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
                    f"{DynamicType.ARTICLE}, {DynamicType.DRAW}, {DynamicType.TEXT}, "
                    f"{DynamicType.REVIEW}. REVIEW includes only recognized "
                    "five-slot rating cards, not other common cards."
                )
            ),
        ] = DynamicType.ALL,
    ) -> Dict[str, Any]:
        """Get user dynamics with type filtering and cursor pagination."""

        async def _runner() -> Dict[str, Any]:
            cred = await _get_credential_from_context(ctx)
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
            cred = await _get_credential_from_context(ctx)
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
            str,
            Field(
                min_length=1,
                description=(
                    "Article id. Accepts a CV id (old format, e.g. 21032785) or "
                    "an opus dynamic id from a bilibili.com/opus/{id} URL "
                    "(e.g. 748254891671027745). Passed as a string because opus "
                    "ids are 64-bit snowflake ids that overflow JS safe integers."
                ),
            ),
        ],
    ) -> Dict[str, Any]:
        """Get full article markdown content (supports both CV and opus ids)."""

        async def _runner() -> Dict[str, Any]:
            cred = await _get_credential_from_context(ctx)
            stripped = article_id.strip()
            if not stripped.isdigit() or int(stripped) < 1:
                raise ToolError(
                    f"article_id must be a positive numeric string, got: {article_id!r}"
                )
            return await fetch_article_content(article_id=stripped, cred=cred)

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
            cred = await _get_credential_from_context(ctx)
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

    MAX_COMMENT_LIMIT = 20
    CommentSortLiteral = Literal["hot", "time"]

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )
    async def get_content_comments(
        ctx: Context,
        content_type: Annotated[
            CommentContentTypeLiteral,
            Field(
                description=(
                    "Content type: video, article, or dynamic. Dynamic IDs are "
                    "resolved to Bilibili's actual comment type and oid."
                )
            ),
        ],
        content_id: Annotated[
            str,
            Field(
                min_length=1,
                description=(
                    "Video BVID/AV/URL, article CV id or opus id, or dynamic/opus "
                    "id. Keep 64-bit IDs as strings."
                ),
            ),
        ],
        cursor: Annotated[
            str | None,
            Field(
                description=(
                    "Pagination cursor from the previous response. Omit for the "
                    "first page and keep sort unchanged while paging."
                )
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_COMMENT_LIMIT,
                description=f"Comments per page, 1-{MAX_COMMENT_LIMIT}.",
            ),
        ] = 20,
        sort: Annotated[
            CommentSortLiteral,
            Field(description="Sort order: hot or time."),
        ] = "hot",
    ) -> Dict[str, Any]:
        """Get top-level comments for a video, article, or dynamic.

        Each comment includes up to 3 preview sub-replies, image metadata, and note
        metadata. Use the comment's `rpid` as `root_rpid` with
        `get_content_comment_replies` to retrieve the complete reply thread. Pagination
        is cursor-based; keep `sort` unchanged while paging. The pinned `top` comment is
        only present on the first page. For a note, pass `note.cvid` to
        `get_article_content` to retrieve its full content; the comment API may return
        only a preview.
        """

        async def _runner() -> Dict[str, Any]:
            cred = await _get_credential_from_context(ctx)
            normalized_id = await _normalize_comment_content_id(
                content_type, content_id
            )
            return await fetch_content_comments(
                content_type=content_type,
                content_id=normalized_id,
                cursor=cursor,
                limit=limit,
                sort=sort,
                cred=cred,
            )

        try:
            return await _run_tool("get_content_comments", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("get_content_comments failed")
            raise ToolError(f"Failed to fetch content comments: {exc}")

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    )
    async def get_content_comment_replies(
        ctx: Context,
        content_type: Annotated[
            CommentContentTypeLiteral,
            Field(description="Content type: video, article, or dynamic."),
        ],
        content_id: Annotated[
            str,
            Field(
                min_length=1,
                description=(
                    "Video BVID/AV/URL, article CV id or opus id, or dynamic/opus "
                    "id. Keep 64-bit IDs as strings."
                ),
            ),
        ],
        root_rpid: Annotated[
            int,
            Field(
                ge=1,
                description=(
                    "Top-level comment rpid returned by `get_content_comments`."
                ),
            ),
        ],
        page: Annotated[
            int,
            Field(ge=1, le=MAX_PAGE, description="Page number starting from 1."),
        ] = 1,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_COMMENT_LIMIT,
                description=f"Replies per page, 1-{MAX_COMMENT_LIMIT}.",
            ),
        ] = 20,
    ) -> Dict[str, Any]:
        """Get paginated replies under one top-level video, article, or dynamic comment."""

        async def _runner() -> Dict[str, Any]:
            cred = await _get_credential_from_context(ctx)
            normalized_id = await _normalize_comment_content_id(
                content_type, content_id
            )
            return await fetch_content_comment_replies(
                content_type=content_type,
                content_id=normalized_id,
                root_rpid=root_rpid,
                page=page,
                limit=limit,
                cred=cred,
            )

        try:
            return await _run_tool("get_content_comment_replies", _runner)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("get_content_comment_replies failed")
            raise ToolError(f"Failed to fetch content comment replies: {exc}")

    return mcp
