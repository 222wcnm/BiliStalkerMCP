import pytest

from bili_stalker_mcp.config import DynamicType
from bili_stalker_mcp.core import (
    _decode_cursor_token,
    _encode_cursor_token,
    _is_dynamic_type_match,
    _normalize_dynamic_type,
)


def test_dynamic_type_contract_values():
    assert DynamicType.VALID_TYPES == (
        "ALL",
        "ALL_RAW",
        "VIDEO",
        "ARTICLE",
        "DRAW",
        "TEXT",
    )


def test_normalize_dynamic_type_is_case_insensitive():
    assert _normalize_dynamic_type("video") == "VIDEO"
    assert _normalize_dynamic_type(" all_raw ") == "ALL_RAW"


def test_normalize_dynamic_type_rejects_invalid_value():
    with pytest.raises(ValueError, match="Invalid dynamic_type"):
        _normalize_dynamic_type("INVALID")


@pytest.mark.parametrize(
    ("item_type", "dynamic_type"),
    [
        ("DYNAMIC_TYPE_FORWARD", DynamicType.ALL),
        ("DYNAMIC_TYPE_DRAW", DynamicType.DRAW),
        ("DYNAMIC_TYPE_WORD", DynamicType.TEXT),
        ("DYNAMIC_TYPE_AV", DynamicType.VIDEO),
        ("DYNAMIC_TYPE_ARTICLE", DynamicType.ARTICLE),
    ],
)
def test_dynamic_type_matching_supports_polymer_types(item_type, dynamic_type):
    assert _is_dynamic_type_match(item_type, dynamic_type) is True


def test_cursor_token_round_trip():
    token = _encode_cursor_token(
        api_cursor="abc123",
        skip_matches=7,
        user_id=42,
        dynamic_type=DynamicType.ALL,
    )
    api_cursor, skip_matches = _decode_cursor_token(
        token,
        user_id=42,
        dynamic_type=DynamicType.ALL,
    )

    assert api_cursor == "abc123"
    assert skip_matches == 7


def test_cursor_token_rejects_user_or_type_mismatch():
    token = _encode_cursor_token(
        api_cursor=0,
        skip_matches=1,
        user_id=1,
        dynamic_type=DynamicType.TEXT,
    )

    with pytest.raises(ValueError, match="Cursor does not belong"):
        _decode_cursor_token(token, user_id=2, dynamic_type=DynamicType.TEXT)

    with pytest.raises(ValueError, match="Cursor does not match"):
        _decode_cursor_token(token, user_id=1, dynamic_type=DynamicType.ALL)
