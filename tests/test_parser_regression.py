from bili_stalker_mcp.core import _parse_dynamic_item


def test_parse_repost_handles_null_origin_user():
    item = {
        "desc": {
            "dynamic_id_str": "123",
            "timestamp": 1771601421,
            "type": 1,
            "origin": {"type": 4},
        },
        "card": {
            "item": {"content": "repost text"},
            "origin_user": None,
            "origin": {"item": {"content": "origin text"}},
        },
    }

    parsed = _parse_dynamic_item(item)

    assert "error" not in parsed
    assert parsed["type"] == "REPOST"
    assert parsed["text_content"] == "repost text"
    assert parsed["origin"]["type"] == "TEXT"
    assert parsed["origin"]["text_content"] == "origin text"
    assert parsed["origin"]["user_name"] is None
    assert parsed["origin"]["user_id"] is None


def test_parse_repost_keeps_origin_user_when_present():
    item = {
        "desc": {
            "dynamic_id_str": "124",
            "timestamp": 1771601421,
            "type": 1,
            "origin": {"type": 4},
        },
        "card": {
            "item": {"content": "repost text"},
            "origin_user": {"info": {"uname": "alice", "uid": 1001}},
            "origin": {"item": {"content": "origin text"}},
        },
    }

    parsed = _parse_dynamic_item(item)

    assert parsed["origin"]["user_name"] == "alice"
    assert parsed["origin"]["user_id"] == 1001


def test_parse_unknown_dynamic_type_does_not_crash():
    item = {
        "desc": {
            "dynamic_id_str": "125",
            "timestamp": 1771601421,
            "type": 9999,
        },
        "card": {},
    }

    parsed = _parse_dynamic_item(item)

    assert "error" not in parsed
    assert parsed["type"] == "UNKNOWN_9999"


def test_parse_repost_handles_null_origin_payload():
    item = {
        "desc": {
            "dynamic_id_str": "126",
            "timestamp": 1771601421,
            "type": 1,
            "origin": {"type": 4},
        },
        "card": {
            "item": {"content": "repost text"},
            "origin_user": {"info": {"uname": "bob", "uid": 1002}},
            "origin": None,
        },
    }

    parsed = _parse_dynamic_item(item)

    assert "error" not in parsed
    assert parsed["type"] == "REPOST"
    assert "origin" not in parsed


def test_parse_dynamic_item_with_non_mapping_card_is_handled_gracefully():
    item = {
        "desc": {
            "dynamic_id_str": "127",
            "timestamp": 1771601421,
            "type": 4,
        },
        "card": None,
    }

    parsed = _parse_dynamic_item(item)

    assert "error" not in parsed
    assert parsed["dynamic_id"] == "127"
    assert parsed["type"] == "TEXT"
