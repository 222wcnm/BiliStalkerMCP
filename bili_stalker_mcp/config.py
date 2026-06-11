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


REQUEST_DELAY = 3.0
REQUEST_TIMEOUT = 60.0
CONNECT_TIMEOUT = 15.0
READ_TIMEOUT = 45.0
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


REQUEST_JITTER_MIN_MS = max(0, _get_env_int("BILI_REQUEST_JITTER_MIN_MS", 200))
REQUEST_JITTER_MAX_MS = max(0, _get_env_int("BILI_REQUEST_JITTER_MAX_MS", 1200))
if REQUEST_JITTER_MAX_MS < REQUEST_JITTER_MIN_MS:
    logger.warning(
        "BILI_REQUEST_JITTER_MAX_MS (%s) is lower than min (%s), clamping to min",
        REQUEST_JITTER_MAX_MS,
        REQUEST_JITTER_MIN_MS,
    )
    REQUEST_JITTER_MAX_MS = REQUEST_JITTER_MIN_MS

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

    _request_settings_initialized = True


class DynamicType:
    """Supported dynamic filter values exposed by the MCP tool contract."""

    ALL: Literal["ALL"] = "ALL"
    ALL_RAW: Literal["ALL_RAW"] = "ALL_RAW"
    VIDEO: Literal["VIDEO"] = "VIDEO"
    ARTICLE: Literal["ARTICLE"] = "ARTICLE"
    DRAW: Literal["DRAW"] = "DRAW"
    TEXT: Literal["TEXT"] = "TEXT"

    VALID_TYPES = (ALL, ALL_RAW, VIDEO, ARTICLE, DRAW, TEXT)

    TYPE_MAPPINGS = {
        ALL: "all",
        ALL_RAW: "all_raw",
        VIDEO: "8",
        ARTICLE: "64",
        DRAW: "2",
        TEXT: "4",
    }
