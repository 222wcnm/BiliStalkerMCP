"""Project-wide runtime and API constants."""

import logging

logger = logging.getLogger(__name__)


try:
    from bilibili_api import request_settings, select_client

    request_settings.set_enable_auto_buvid(True)

    try:
        select_client("curl_cffi")
        request_settings.set("impersonate", "chrome131")
        logger.debug("Using curl_cffi client with chrome131 impersonation")
    except Exception as exc:
        logger.debug("curl_cffi client unavailable, using default client: %s", exc)
except ImportError:
    logger.warning("bilibili_api is not installed, skipping request settings initialization")


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


class DynamicType:
    """Supported dynamic filter values exposed by the MCP tool contract."""

    ALL = "ALL"
    ALL_RAW = "ALL_RAW"
    VIDEO = "VIDEO"
    ARTICLE = "ARTICLE"
    DRAW = "DRAW"
    TEXT = "TEXT"

    VALID_TYPES = (ALL, ALL_RAW, VIDEO, ARTICLE, DRAW, TEXT)

    TYPE_MAPPINGS = {
        ALL: "all",
        ALL_RAW: "all_raw",
        VIDEO: "8",
        ARTICLE: "64",
        DRAW: "2",
        TEXT: "4",
    }
