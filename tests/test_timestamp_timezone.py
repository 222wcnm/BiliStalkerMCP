from datetime import timedelta, timezone

from bili_stalker_mcp.parsers import dynamic_parser


def test_format_timestamp_uses_configured_timezone(monkeypatch):
    monkeypatch.setattr(dynamic_parser, "_OUTPUT_TZ", timezone(timedelta(hours=8)))
    assert dynamic_parser.format_timestamp(0) == "1970-01-01 08:00"
