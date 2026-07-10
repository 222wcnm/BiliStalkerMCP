from bili_stalker_mcp.parsers.dynamic_parser import parse_dynamic_item


def test_parse_polymer_draw_extracts_content_stats_and_images():
    item = {
        "id_str": "3001",
        "type": "DYNAMIC_TYPE_DRAW",
        "modules": {
            "module_author": {"pub_ts": "1771601421"},
            "module_dynamic": {
                "desc": None,
                "major": {
                    "opus": {
                        "summary": {"text": "polymer draw"},
                        "pics": [
                            {
                                "url": "https://example.com/1.jpg",
                                "width": "1920",
                                "height": 1080,
                            },
                            {"url": "   ", "width": 100, "height": 100},
                            {
                                "url": "https://example.com/2.jpg",
                                "width": "invalid",
                                "height": 720.9,
                            },
                            {"url": None},
                        ],
                    }
                },
            },
            "module_stat": {
                "like": {"count": 11},
                "comment": {"count": "7"},
                "forward": {"count": 3},
            },
        },
    }

    parsed = parse_dynamic_item(item)

    assert parsed["dynamic_id"] == "3001"
    assert parsed["publish_time"] == "2026-02-20 23:30"
    assert parsed["type"] == "DRAW"
    assert parsed["text_content"] == "polymer draw"
    assert parsed["image_count"] == 2
    assert parsed["images"] == [
        {
            "url": "https://example.com/1.jpg",
            "width": 1920,
            "height": 1080,
        },
        {
            "url": "https://example.com/2.jpg",
            "width": None,
            "height": 720,
        },
    ]
    assert parsed["stats"] == {"like": 11, "comment": 7, "forward": 3}


def test_parse_polymer_draw_items_extracts_images():
    item = {
        "id_str": "3002",
        "type": "DYNAMIC_TYPE_DRAW",
        "modules": {
            "module_author": {"pub_ts": "1771601421"},
            "module_dynamic": {
                "major": {
                    "draw": {
                        "items": [
                            {
                                "src": "https://example.com/draw.jpg",
                                "width": "640",
                                "height": "480",
                            },
                            {"src": 123, "width": 320, "height": 240},
                        ]
                    }
                }
            },
            "module_stat": {},
        },
    }

    parsed = parse_dynamic_item(item)

    assert parsed["type"] == "DRAW"
    assert parsed["image_count"] == 1
    assert parsed["images"] == [
        {
            "url": "https://example.com/draw.jpg",
            "width": 640,
            "height": 480,
        }
    ]


def test_parse_unknown_polymer_dynamic_type_returns_unknown_and_logs(caplog):
    item = {
        "id_str": "3005",
        "type": "DYNAMIC_TYPE_FUTURE_CARD",
        "modules": {
            "module_author": {"pub_ts": "1771601421"},
            "module_dynamic": {
                "desc": {"text": "future card"},
                "major": {
                    "common": {"title": "future title"},
                },
            },
            "module_stat": {
                "like": {"count": 5},
                "comment": {"count": 2},
                "forward": {"count": 1},
            },
        },
    }

    with caplog.at_level(
        "DEBUG",
        logger="bili_stalker_mcp.parsers.dynamic_parser",
    ):
        parsed = parse_dynamic_item(item)

    assert "error" not in parsed
    assert parsed["type"] == "UNKNOWN_FUTURE_CARD"
    assert parsed["text_content"] == "future card"
    assert parsed["stats"] == {"like": 5, "comment": 2, "forward": 1}
    assert any(
        record.message.startswith("unhandled dynamic type: DYNAMIC_TYPE_FUTURE_CARD")
        for record in caplog.records
    )


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
                    {
                        "img_src": "https://example.com/1.jpg",
                        "img_width": "1280",
                        "img_height": 720,
                    },
                    {
                        "img_src": "https://example.com/2.jpg",
                        "img_width": None,
                        "img_height": "bad",
                    },
                    {"img_src": ""},
                    {"img_src": 123},
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
    assert parsed["images"] == [
        {
            "url": "https://example.com/1.jpg",
            "width": 1280,
            "height": 720,
        },
        {
            "url": "https://example.com/2.jpg",
            "width": None,
            "height": None,
        },
    ]


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
                    "pictures": [
                        {
                            "img_src": "https://example.com/a.jpg",
                            "img_width": "800",
                            "img_height": "600",
                        }
                    ],
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
    assert parsed["origin"]["images"] == [
        {
            "url": "https://example.com/a.jpg",
            "width": 800,
            "height": 600,
        }
    ]


def test_parse_polymer_repost_origin_keeps_images():
    item = {
        "id_str": "3003",
        "type": "DYNAMIC_TYPE_FORWARD",
        "modules": {
            "module_author": {"pub_ts": "1771601421"},
            "module_dynamic": {"desc": {"text": "forward text"}},
            "module_stat": {},
        },
        "orig": {
            "id_str": "3004",
            "type": "DYNAMIC_TYPE_DRAW",
            "modules": {
                "module_author": {
                    "pub_ts": "1771601400",
                    "name": "bob",
                    "mid": "1002",
                },
                "module_dynamic": {
                    "major": {
                        "opus": {
                            "pics": [
                                {
                                    "url": "https://example.com/origin.jpg",
                                    "width": "1024",
                                    "height": "768",
                                }
                            ]
                        }
                    }
                },
                "module_stat": {},
            },
        },
    }

    parsed = parse_dynamic_item(item)

    assert parsed["type"] == "REPOST"
    assert parsed["images"] == []
    assert parsed["origin"]["type"] == "DRAW"
    assert parsed["origin"]["image_count"] == 1
    assert parsed["origin"]["images"] == [
        {
            "url": "https://example.com/origin.jpg",
            "width": 1024,
            "height": 768,
        }
    ]
    assert parsed["origin"]["user_name"] == "bob"
    assert parsed["origin"]["user_id"] == 1002
