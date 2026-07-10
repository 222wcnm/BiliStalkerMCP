import logging
from typing import Optional

from bilibili_api import user  # compatibility export for tests/monkeypatching
from bilibili_api import Credential

from .config import initialize_bilibili_request_settings
from .credentials import CredentialLoadError, load_credential_snapshot
from .infra.http_client import get_shared_http_client
from .parsers.dynamic_parser import format_timestamp, parse_dynamic_item
from .services.comment_service import (
    fetch_content_comment_replies,
    fetch_content_comments,
)
from .services.dynamic_service import (
    decode_cursor_token,
    encode_cursor_token,
    fetch_user_dynamics,
    is_dynamic_type_match,
    normalize_dynamic_type,
)
from .services.user_service import (
    fetch_article_content,
    fetch_user_articles,
    fetch_user_followings,
    fetch_user_info,
    fetch_user_videos,
    fetch_video_detail,
    get_user_id_by_username,
)

initialize_bilibili_request_settings()

logger = logging.getLogger(__name__)

_credential_cache_key: tuple[str | bool | None, ...] | None = None
_credential_cache_value: Credential | None = None
_missing_buvid3_warned = False


def get_credential() -> Optional[Credential]:
    """Build Bilibili credential from environment variables and cookie files.

    This function caches by resolved credential values to keep identity stable,
    allowing async-lru caches keyed by credential object to hit reliably.
    """
    global _credential_cache_key, _credential_cache_value, _missing_buvid3_warned

    try:
        snapshot = load_credential_snapshot()
    except CredentialLoadError as exc:
        logger.error("Failed to load credential configuration: %s", exc)
        _credential_cache_key = None
        _credential_cache_value = None
        return None

    if not snapshot.sessdata:
        logger.error("SESSDATA is not configured; set SESSDATA or BILI_COOKIE_FILE")
        _credential_cache_key = None
        _credential_cache_value = None
        return None

    current_key = snapshot.cache_key()
    if _credential_cache_key == current_key and _credential_cache_value is not None:
        return _credential_cache_value

    try:
        if not snapshot.buvid3 and not _missing_buvid3_warned:
            logger.warning(
                "BUVID3 is not set; anti-bot block risk is higher for raw requests"
            )
            _missing_buvid3_warned = True

        if not snapshot.bili_jct:
            logger.warning("Using minimal authentication (SESSDATA only)")

        credential = snapshot.to_credential()
        if credential is None:
            _credential_cache_key = None
            _credential_cache_value = None
            return None

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
    "user",
    "get_credential",
    "get_user_id_by_username",
    "fetch_user_info",
    "fetch_user_videos",
    "fetch_video_detail",
    "fetch_user_dynamics",
    "fetch_user_articles",
    "fetch_article_content",
    "fetch_user_followings",
    "fetch_content_comments",
    "fetch_content_comment_replies",
    "_format_timestamp",
    "_get_shared_http_client",
    "_normalize_dynamic_type",
    "_is_dynamic_type_match",
    "_encode_cursor_token",
    "_decode_cursor_token",
    "_parse_dynamic_item",
]
