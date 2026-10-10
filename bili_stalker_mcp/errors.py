"""Public-safe error summaries for MCP clients and logs."""

import json
import math
from dataclasses import dataclass
from typing import Any

import httpx

RISK_CONTROL_CODES = {-412, 412}
RISK_CONTROL_MESSAGE = (
    "Bilibili returned 412 or the shared risk-control circuit is open. "
    "Respect retry_after (seconds) before further upstream requests; "
    "if absent, pause and retry later. Use already retrieved data where sufficient."
)


@dataclass(frozen=True)
class PublicError:
    code: int | None
    reason: str
    retry_after: int | None
    message: str
    request_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "reason": self.reason,
            "retry_after": self.retry_after,
            "message": self.message,
        }
        if self.request_id:
            payload["request_id"] = self.request_id
        return payload

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"))


class RiskControlError(Exception):
    """Raised when Bilibili 412 risk control is observed or the circuit is open."""

    code = 412
    reason = "risk_control"

    def __init__(self, *, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(risk_control_error(retry_after=retry_after).to_json())


class InvalidVideoIdentifierError(ValueError):
    """Input could not be normalized to a video identifier."""

    reason = "invalid_video_identifier"
    message = "Provide a valid 12-character BVID, AV number, or Bilibili video URL."

    def __init__(self) -> None:
        super().__init__(self.message)


class ShortLinkResolutionError(InvalidVideoIdentifierError):
    """A short link failed to resolve to a video identifier."""

    reason = "short_link_resolution_failed"
    message = (
        "Could not resolve the b23.tv link to a video. "
        "Provide the full Bilibili video URL or BVID, or retry later."
    )


class InvalidSubtitleSelectionError(ValueError):
    """A subtitle scope or page selection is invalid or conflicting."""

    reason = "invalid_subtitle_selection"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def normalize_retry_after(seconds: float | int | None) -> int | None:
    if seconds is None:
        return None
    return max(0, int(math.ceil(float(seconds))))


def risk_control_error(
    *,
    retry_after: float | int | None = None,
    request_id: str | None = None,
) -> PublicError:
    return PublicError(
        code=412,
        reason="risk_control",
        retry_after=normalize_retry_after(retry_after),
        message=RISK_CONTROL_MESSAGE,
        request_id=request_id,
    )


def extract_error_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code

    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status

    if exc.args:
        first = exc.args[0]
        if isinstance(first, dict):
            arg_code = first.get("code")
            if isinstance(arg_code, int):
                return arg_code

    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code

    return None


def public_error_from_exception(
    exc: Exception,
    *,
    request_id: str | None = None,
) -> PublicError:
    if isinstance(exc, (InvalidVideoIdentifierError, InvalidSubtitleSelectionError)):
        return PublicError(
            code=None,
            reason=exc.reason,
            retry_after=None,
            message=exc.message,
            request_id=request_id,
        )

    if isinstance(exc, RiskControlError):
        return risk_control_error(
            retry_after=exc.retry_after,
            request_id=request_id,
        )

    code = extract_error_code(exc)
    if code in RISK_CONTROL_CODES:
        retry_after = getattr(exc, "retry_after", None)
        if not isinstance(retry_after, (int, float)) or isinstance(retry_after, bool):
            retry_after = None
        return risk_control_error(
            retry_after=retry_after,
            request_id=request_id,
        )

    return PublicError(
        code=code,
        reason="upstream_error" if code is not None else "internal_error",
        retry_after=None,
        message="BiliStalkerMCP request failed.",
        request_id=request_id,
    )


def public_error_json(
    exc: Exception,
    *,
    request_id: str | None = None,
    tool: str | None = None,
    section: str | None = None,
) -> str:
    payload = public_error_from_exception(exc, request_id=request_id).as_dict()
    if payload["reason"] == "risk_control":
        # These identify the affected operation, not the endpoint that caused
        # the shared circuit to open. Callers supply static names, never URLs.
        if tool:
            payload["tool"] = tool
        if section:
            payload["section"] = section
        if tool in {"get_user_videos", "search_user_videos"} or (
            tool == "get_user_snapshot" and section == "videos"
        ):
            payload["message"] += (
                ' For recent video clues, get_user_dynamics with dynamic_type="VIDEO" '
                "may help after the cooldown, or use dynamics already retrieved. "
                "Dynamics are not a complete upload list or a substitute for video search."
            )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
