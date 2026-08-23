"""Project-wide runtime and API constants."""

import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "sec-ch-ua": '"Google Chrome";v="131", "Not=A?Brand";v="8", "Chromium";v="131"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-model": '""',
    "sec-ch-ua-arch": '"x86"',
    "sec-ch-ua-bitness": '"64"',
    "sec-ch-ua-full-version-list": '"Google Chrome";v="131.0.0.0", "Not=A?Brand";v="8.0.0.0", "Chromium";v="131.0.0.0"',
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
    "DNT": "1",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "sec-gpc": "1",
}


def _get_env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default

    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid float value for %s=%r, falling back to %s", name, raw, default
        )
        return default


REQUEST_DELAY = 3.0
# Per-attempt upstream timeouts. Kept well below typical MCP client deadlines so a
# stalled upstream request fails fast instead of blocking the whole tool call.
REQUEST_TIMEOUT = _get_env_float("BILI_REQUEST_TIMEOUT_SECONDS", 20.0)
CONNECT_TIMEOUT = _get_env_float("BILI_CONNECT_TIMEOUT_SECONDS", 10.0)
READ_TIMEOUT = _get_env_float("BILI_READ_TIMEOUT_SECONDS", 15.0)
DEFAULT_TIMEZONE = os.environ.get("BILI_TIMEZONE", "Asia/Shanghai")
DEFAULT_IMPERSONATE: Literal["chrome131"] = "chrome131"


def _get_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default

    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid integer value for %s=%r, falling back to %s", name, raw, default
        )
        return default


def _get_env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default

    cleaned = raw.strip()
    if not cleaned:
        logger.warning("Empty value for %s, falling back to %r", name, default)
        return default
    return cleaned


def _get_env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logger.warning(
        "Invalid boolean value for %s=%r, falling back to %s", name, raw, default
    )
    return default


# Upstream proxy shared by bilibili_api and the raw HTTP clients. bilibili_api's
# curl_cffi client overrides environment proxies with an empty string, so an
# explicit proxy must be applied through request_settings to take effect.
PROXY_URL = _get_env_str("BILI_PROXY", "")

REQUEST_JITTER_MIN_MS = max(0, _get_env_int("BILI_REQUEST_JITTER_MIN_MS", 200))
REQUEST_JITTER_MAX_MS = max(0, _get_env_int("BILI_REQUEST_JITTER_MAX_MS", 1200))
if REQUEST_JITTER_MAX_MS < REQUEST_JITTER_MIN_MS:
    logger.warning(
        "BILI_REQUEST_JITTER_MAX_MS (%s) is lower than min (%s), clamping to min",
        REQUEST_JITTER_MAX_MS,
        REQUEST_JITTER_MIN_MS,
    )
    REQUEST_JITTER_MAX_MS = REQUEST_JITTER_MIN_MS


def _get_env_jitter_mode() -> str:
    raw = os.environ.get("BILI_REQUEST_JITTER_MODE")
    if raw is None:
        return "adaptive"

    cleaned = raw.strip().lower()
    if cleaned in {"adaptive", "always", "never"}:
        return cleaned

    logger.warning("Invalid BILI_REQUEST_JITTER_MODE=%r, falling back to adaptive", raw)
    return "adaptive"


# "adaptive": jitter only when anonymous (no SESSDATA) or after recent
# risk-control pressure; "always"/"never" force the behavior unconditionally.
REQUEST_JITTER_MODE = _get_env_jitter_mode()
# Total jitter sleep budget per tool call; further upstream calls skip once used up.
REQUEST_JITTER_BUDGET_MS = max(0, _get_env_int("BILI_REQUEST_JITTER_BUDGET_MS", 500))
# How long a 412/429/403 keeps the adaptive jitter engaged.
RISK_PRESSURE_WINDOW_SECONDS = max(
    1, _get_env_int("BILI_RISK_PRESSURE_WINDOW_SECONDS", 300)
)

BILI_412_CIRCUIT_THRESHOLD = max(1, _get_env_int("BILI_412_CIRCUIT_THRESHOLD", 3))
BILI_412_CIRCUIT_WINDOW_SECONDS = max(
    1,
    _get_env_int("BILI_412_CIRCUIT_WINDOW_SECONDS", 600),
)
BILI_412_CIRCUIT_COOLDOWN_SECONDS = max(
    1,
    _get_env_int("BILI_412_CIRCUIT_COOLDOWN_SECONDS", 1800),
)

LAZY_ENABLED = _get_env_bool("BILI_LAZY_ENABLED", True)
LAZY_DYNAMICS_BATCH = max(1, _get_env_int("BILI_LAZY_DYNAMICS_BATCH", 30))
LAZY_SLEEP_MIN_SECONDS = max(0, _get_env_int("BILI_LAZY_SLEEP_MIN_SECONDS", 5))
LAZY_SLEEP_MAX_SECONDS = max(0, _get_env_int("BILI_LAZY_SLEEP_MAX_SECONDS", 20))
if LAZY_SLEEP_MAX_SECONDS < LAZY_SLEEP_MIN_SECONDS:
    logger.warning(
        "BILI_LAZY_SLEEP_MAX_SECONDS (%s) is lower than min (%s), clamping to min",
        LAZY_SLEEP_MAX_SECONDS,
        LAZY_SLEEP_MIN_SECONDS,
    )
    LAZY_SLEEP_MAX_SECONDS = LAZY_SLEEP_MIN_SECONDS

_request_settings_initialized = False


def initialize_bilibili_request_settings() -> None:
    """Apply request settings once for bilibili_api."""
    global _request_settings_initialized

    if _request_settings_initialized:
        return

    try:
        from bilibili_api import request_settings, select_client
    except ImportError:
        logger.warning(
            "bilibili_api is not installed, skipping request settings initialization"
        )
        return

    request_settings.set_enable_auto_buvid(True)
    request_settings.set("headers", DEFAULT_HEADERS)
    request_settings.set("timeout", REQUEST_TIMEOUT)

    try:
        select_client("curl_cffi")
        request_settings.set("impersonate", DEFAULT_IMPERSONATE)
        logger.debug(
            "Using curl_cffi client with %s impersonation", DEFAULT_IMPERSONATE
        )
    except Exception as exc:
        logger.debug("curl_cffi client unavailable, using default client: %s", exc)

    if PROXY_URL:
        try:
            request_settings.set_proxy(PROXY_URL)
            logger.debug("Routing bilibili_api requests through proxy %s", PROXY_URL)
        except Exception as exc:
            logger.warning(
                "Failed to configure bilibili_api proxy %s: %s", PROXY_URL, exc
            )

    _request_settings_initialized = True


class DynamicType:
    """Supported dynamic filter values exposed by the MCP tool contract."""

    ALL: Literal["ALL"] = "ALL"
    ALL_RAW: Literal["ALL_RAW"] = "ALL_RAW"
    VIDEO: Literal["VIDEO"] = "VIDEO"
    ARTICLE: Literal["ARTICLE"] = "ARTICLE"
    DRAW: Literal["DRAW"] = "DRAW"
    TEXT: Literal["TEXT"] = "TEXT"
    REVIEW: Literal["REVIEW"] = "REVIEW"

    VALID_TYPES = (ALL, ALL_RAW, VIDEO, ARTICLE, DRAW, TEXT, REVIEW)

    TYPE_MAPPINGS = {
        ALL: "all",
        ALL_RAW: "all_raw",
        VIDEO: "8",
        ARTICLE: "64",
        DRAW: "2",
        TEXT: "4",
    }
