import logging
import os
from typing import Any, Optional

import bilibili_api
from bilibili_api import Credential
from bilibili_api import user  # compatibility export for tests/monkeypatching

from .config import DEFAULT_HEADERS, REQUEST_TIMEOUT
from .infra.http_client import get_shared_http_client
from .parsers.dynamic_parser import format_timestamp, parse_dynamic_item
from .services.dynamic_service import (
    decode_cursor_token,
    encode_cursor_token,
    fetch_user_dynamics,
    is_dynamic_type_match,
    normalize_dynamic_type,
)
from .services.user_service import (
    _get_video_subtitle_info,
    fetch_user_articles,
    fetch_user_followings,
    fetch_user_info,
    fetch_user_videos,
    get_user_id_by_username,
)


bilibili_api.request_settings.set("headers", DEFAULT_HEADERS)
bilibili_api.request_settings.set("timeout", REQUEST_TIMEOUT)

logger = logging.getLogger(__name__)

_credential_cache_key: tuple[str | None, str | None, str | None] | None = None
_credential_cache_value: Credential | None = None


def get_credential() -> Optional[Credential]:
    """Build Bilibili credential from environment variables.

    This function caches by raw env tuple to keep identity stable across calls,
    allowing async-lru caches keyed by credential object to hit reliably.
    """
    global _credential_cache_key, _credential_cache_value

    sessdata = os.environ.get("SESSDATA")
    bili_jct = os.environ.get("BILI_JCT")
    buvid3 = os.environ.get("BUVID3")

    if not sessdata:
        logger.error("SESSDATA is not set in environment variables")
        _credential_cache_key = None
        _credential_cache_value = None
        return None

    current_key = (sessdata, bili_jct, buvid3)
    if _credential_cache_key == current_key and _credential_cache_value is not None:
        return _credential_cache_value

    try:
        if bili_jct and buvid3:
            credential = Credential(sessdata=sessdata, bili_jct=bili_jct, buvid3=buvid3)
        elif bili_jct:
            credential = Credential(sessdata=sessdata, bili_jct=bili_jct, buvid3="")
        else:
            logger.warning("Using minimal authentication (SESSDATA only)")
            credential = Credential(sessdata=sessdata, bili_jct="", buvid3="")

        _credential_cache_key = current_key
        _credential_cache_value = credential
        return credential
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to create credential object: %s", exc)
        _credential_cache_key = None
        _credential_cache_value = None
        return None


# Compatibility exports for existing callers/tests.
_format_timestamp = format_timestamp
_get_shared_http_client = get_shared_http_client
_normalize_dynamic_type = normalize_dynamic_type
_is_dynamic_type_match = is_dynamic_type_match
_encode_cursor_token = encode_cursor_token
_decode_cursor_token = decode_cursor_token
_parse_dynamic_item = parse_dynamic_item


__all__ = [
    "get_credential",
    "get_user_id_by_username",
    "fetch_user_info",
    "fetch_user_videos",
    "fetch_user_dynamics",
    "fetch_user_articles",
    "fetch_user_followings",
    "_get_video_subtitle_info",
    "_format_timestamp",
    "_get_shared_http_client",
    "_normalize_dynamic_type",
    "_is_dynamic_type_match",
    "_encode_cursor_token",
    "_decode_cursor_token",
    "_parse_dynamic_item",
]
