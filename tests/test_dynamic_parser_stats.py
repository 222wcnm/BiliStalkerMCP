from bili_stalker_mcp.parsers.dynamic_parser import parse_dynamic_item


def test_parse_draw_extracts_stats_and_image_count():
    item = {
        "desc": {
            "dynamic_id_str": "2001",
            "timestamp": 1771601421,
            "type": 2,
            "like": "11",
            "comment": 7,
            "repost": "3",
        },
        "card": {
            "item": {
                "description": "draw content",
                "pictures": [
                    {"img_src": "https://example.com/1.jpg"},
                    {"img_src": "https://example.com/2.jpg"},
                    None,
                ],
            }
        },
    }

    parsed = parse_dynamic_item(item)

    assert parsed["type"] == "DRAW"
    assert parsed["text_content"] == "draw content"
    assert parsed["image_count"] == 2
    assert parsed["stats"] == {"like": 11, "comment": 7, "forward": 3}
    assert "images" not in parsed


def test_parse_repost_origin_keeps_structured_origin_and_forward_fallback():
    item = {
        "desc": {
            "dynamic_id_str": "2002",
            "timestamp": 1771601421,
            "type": 1,
            "like": 1,
            "comment": 2,
            "forward": 9,
            "origin": {"type": 2},
        },
        "card": {
            "item": {"content": "repost content"},
            "origin_user": {"info": {"uname": "alice", "uid": "1001"}},
            "origin": {
                "item": {
                    "description": "origin draw",
                    "pictures": [{"img_src": "https://example.com/a.jpg"}],
                }
            },
        },
    }

    parsed = parse_dynamic_item(item)

    assert parsed["type"] == "REPOST"
    assert parsed["stats"] == {"like": 1, "comment": 2, "forward": 9}
    assert parsed["origin"]["type"] == "DRAW"
    assert parsed["origin"]["text_content"] == "origin draw"
    assert parsed["origin"]["image_count"] == 1
    assert parsed["origin"]["user_name"] == "alice"
    assert parsed["origin"]["user_id"] == 1001
    assert "images" not in parsed["origin"]
