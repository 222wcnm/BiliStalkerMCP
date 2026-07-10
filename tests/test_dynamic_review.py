import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from bili_stalker_mcp import core
from bili_stalker_mcp.models import DynamicItemResponse
from bili_stalker_mcp.parsers.dynamic_parser import (
    is_review_dynamic_item,
    parse_dynamic_item,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dynamic_review.json"


def _load_review_card() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _module_dynamic(card: dict[str, Any]) -> dict[str, Any]:
    return card["modules"]["module_dynamic"]


def test_parse_five_star_review_extracts_review_fields():
    card = _load_review_card()

    parsed = parse_dynamic_item(card)

    assert is_review_dynamic_item(card) is True
    assert parsed["type"] == "REVIEW"
    assert parsed["text_content"] == "这是一条中性测试点评。"
    assert parsed["review"] == {
        "rating": 5,
        "text": "这是一条中性测试点评。",
        "title": "示例作品",
        "cover_url": "https://example.com/review-cover.jpg",
        "jump_url": "https://www.bilibili.com/bangumi/media/md12345",
        "score_description": "9.5分",
        "biz_type": "1",
        "biz_id": "12345",
    }


def test_parse_review_with_empty_stars_counts_only_filled_stars():
    card = _load_review_card()
    _module_dynamic(card)["desc"]["text"] = "[星][星][星][空星][空星]\n三星测试点评。"

    parsed = parse_dynamic_item(card)

    assert parsed["type"] == "REVIEW"
    assert parsed["text_content"] == "三星测试点评。"
    assert "[星]" not in parsed["text_content"]
    assert "[空星]" not in parsed["text_content"]
    assert parsed["review"]["rating"] == 3
    assert parsed["review"]["text"] == "三星测试点评。"
    assert parsed["review"]["score_description"] == "9.5分"


@pytest.mark.parametrize("missing_field", ["desc", "major", "common"])
def test_review_parser_safely_degrades_when_structure_is_missing(missing_field: str):
    card = _load_review_card()
    module_dynamic = _module_dynamic(card)
    if missing_field == "desc":
        module_dynamic.pop("desc")
    elif missing_field == "major":
        module_dynamic.pop("major")
    else:
        module_dynamic["major"].pop("common")

    parsed = parse_dynamic_item(card)

    assert is_review_dynamic_item(card) is False
    assert parsed["type"] == "UNKNOWN_COMMON_SQUARE"
    assert parsed.get("review") is None


@pytest.mark.parametrize(
    "text",
    [
        "普通通用卡片正文",
        "[星][星][星][星]\n不足五星制标记",
        "[星][星][星][星][星][空星]\n超过五星制标记",
        "正文在前\n[星][星][星][星][星]",
    ],
)
def test_non_review_common_square_stays_unknown(text: str):
    card = _load_review_card()
    _module_dynamic(card)["desc"]["text"] = text

    parsed = parse_dynamic_item(card)

    assert is_review_dynamic_item(card) is False
    assert parsed["type"] == "UNKNOWN_COMMON_SQUARE"
    assert parsed.get("review") is None


@pytest.mark.asyncio
async def test_review_filter_excludes_non_rating_common_square(monkeypatch):
    review_card = _load_review_card()
    common_card = deepcopy(review_card)
    common_card["id_str"] = "common-1002"
    _module_dynamic(common_card)["desc"]["text"] = "普通通用卡片正文"

    class FakeUser:
        def __init__(self, uid: int, credential: object):
            self.uid = uid
            self.credential = credential

        async def get_dynamics_new(self, offset: str) -> dict[str, Any]:
            return {
                "items": [common_card, review_card],
                "has_more": False,
                "offset": "",
            }

    monkeypatch.setattr(core.user, "User", FakeUser)
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MIN_MS", 0)
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MAX_MS", 0)

    result = await core.fetch_user_dynamics(
        user_id=1,
        limit=2,
        cred=object(),
        dynamic_type="REVIEW",
    )

    assert result["filter_type"] == "REVIEW"
    assert result["total_fetched"] == 1
    assert [item["dynamic_id"] for item in result["dynamics"]] == ["review-1001"]
    assert result["dynamics"][0]["type"] == "REVIEW"
    assert result["dynamics"][0]["review"]["rating"] == 5


def test_dynamic_review_schema_is_additive_and_optional():
    legacy_item = DynamicItemResponse(
        dynamic_id="legacy-1",
        type="TEXT",
        text_content="旧响应仍可反序列化",
    )

    assert legacy_item.review is None

    schema = DynamicItemResponse.model_json_schema()
    review_schema = schema["$defs"]["DynamicReviewRef"]
    assert "review" in schema["properties"]
    assert "review" not in schema.get("required", [])
    assert set(review_schema["properties"]) == {
        "rating",
        "text",
        "title",
        "cover_url",
        "jump_url",
        "score_description",
        "biz_type",
        "biz_id",
    }
    assert review_schema.get("required", []) == []
