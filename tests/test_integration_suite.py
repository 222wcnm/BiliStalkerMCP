from scripts import integration_suite


def test_validate_dynamic_fields_uses_current_response_contract():
    dynamic = {
        "dynamic_id": "123",
        "publish_time": "2026-06-11 12:00",
        "type": "REPOST",
        "text_content": None,
        "video": None,
    }

    assert integration_suite.validate_dynamic_fields(dynamic) is True
