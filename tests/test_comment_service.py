from typing import Any

import pytest
from bilibili_api import bvid2aid

from bili_stalker_mcp.errors import RiskControlError
from bili_stalker_mcp.infra.circuit_breaker import reset_risk_control_circuit
from bili_stalker_mcp.services import comment_service

BVID = "BV17x411w7KC"
AID = 170001
MAIN_URL = "https://api.bilibili.com/x/v2/reply/main"
REPLIES_URL = "https://api.bilibili.com/x/v2/reply/reply"


@pytest.fixture(autouse=True)
def reset_circuit():
    reset_risk_control_circuit()
    yield
    reset_risk_control_circuit()


def _comment(rpid: int, preview_count: int = 0) -> dict[str, Any]:
    return {
        "rpid": rpid,
        "content": {"message": f"comment-{rpid}"},
        "member": {"mid": str(rpid), "uname": f"user-{rpid}"},
        "like": rpid,
        "rcount": preview_count,
        "ctime": 1771601421,
        "replies": [
            {
                "rpid": rpid * 100 + index,
                "content": {"message": f"preview-{rpid}-{index}"},
                "member": {"mid": str(index), "uname": f"preview-user-{index}"},
                "like": 0,
                "rcount": 0,
                "ctime": 1771601421,
            }
            for index in range(preview_count)
        ],
    }


def _main_response(comment_count: int = 1) -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "replies": [
                _comment(index + 1, preview_count=3) for index in range(comment_count)
            ],
            "cursor": {
                "all_count": comment_count + 10,
                "is_end": False,
                "next": 123456,
            },
        },
    }


def _replies_response(reply_count: int = 1) -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "replies": [_comment(index + 1) for index in range(reply_count)],
            "page": {"count": reply_count + 10},
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("comment_count", [1, 20])
async def test_main_comments_use_one_request_without_n_plus_one(
    monkeypatch, comment_count
):
    calls = []

    async def fake_get_json(url, *, params, cred):
        calls.append((url, params, cred))
        return _main_response(comment_count)

    monkeypatch.setattr(comment_service, "get_json", fake_get_json)

    result = await comment_service.fetch_content_comments(
        content_type="video",
        content_id=BVID,
        cursor=None,
        limit=20,
        sort="hot",
        cred=None,
    )

    assert len(calls) == 1
    assert calls[0][0] == MAIN_URL
    assert calls[0][1] == {
        "type": 1,
        "oid": AID,
        "mode": 3,
        "ps": 20,
    }
    assert result["count"] == comment_count
    assert all(len(comment["replies"]) == 3 for comment in result["comments"])


@pytest.mark.asyncio
async def test_main_comments_forward_cursor_without_fetching_full_replies(monkeypatch):
    calls = []
    sleep_calls = []

    async def fake_get_json(url, *, params, cred):
        calls.append((url, params, cred))
        return _main_response(2)

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(comment_service, "get_json", fake_get_json)
    monkeypatch.setattr(comment_service.asyncio, "sleep", fake_sleep)

    result = await comment_service.fetch_content_comments(
        content_type="video",
        content_id=BVID,
        cursor="987654",
        limit=10,
        sort="time",
        cred=None,
    )

    assert len(calls) == 1
    assert calls[0][0] == MAIN_URL
    assert calls[0][1] == {
        "type": 1,
        "oid": AID,
        "mode": 2,
        "ps": 10,
        "next": "987654",
    }
    assert result["next_cursor"] == "123456"
    assert result["has_more"] is True
    assert len(sleep_calls) == 1


@pytest.mark.asyncio
async def test_comment_replies_use_one_request_with_page_parameters(monkeypatch):
    calls = []
    sleep_calls = []

    async def fake_get_json(url, *, params, cred):
        calls.append((url, params, cred))
        return _replies_response(4)

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(comment_service, "get_json", fake_get_json)
    monkeypatch.setattr(comment_service.asyncio, "sleep", fake_sleep)

    result = await comment_service.fetch_content_comment_replies(
        content_type="video",
        content_id=BVID,
        root_rpid=7654321,
        page=3,
        limit=4,
        cred=None,
    )

    assert len(calls) == 1
    assert calls[0][0] == REPLIES_URL
    assert calls[0][1] == {
        "type": 1,
        "oid": AID,
        "root": 7654321,
        "ps": 4,
        "pn": 3,
    }
    assert result["count"] == 4
    assert result["page"] == 3
    assert result["has_more"] is True
    assert len(sleep_calls) == 1


@pytest.mark.asyncio
async def test_comment_api_retries_rate_limit_code(monkeypatch):
    calls = []

    async def fake_get_json(url, *, params, cred):
        calls.append(url)
        if len(calls) == 1:
            return {"code": -509, "message": "retry"}
        return _main_response()

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(comment_service, "get_json", fake_get_json)
    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)

    result = await comment_service.fetch_content_comments(
        content_type="video",
        content_id=BVID,
        cursor=None,
        limit=20,
        sort="hot",
        cred=None,
    )

    assert result["count"] == 1
    assert calls == [MAIN_URL, MAIN_URL]


@pytest.mark.asyncio
async def test_comment_api_does_not_retry_risk_control_code(monkeypatch):
    calls = []
    sleep_calls = []

    async def fake_get_json(url, *, params, cred):
        calls.append(url)
        return {"code": -412, "message": "blocked"}

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(comment_service, "get_json", fake_get_json)
    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)

    with pytest.raises(RiskControlError):
        await comment_service.fetch_content_comments(
            content_type="video",
            content_id=BVID,
            cursor=None,
            limit=20,
            sort="hot",
            cred=None,
        )

    assert calls == [MAIN_URL]
    assert sleep_calls == []


def test_bvid2aid_conversion_is_local_and_correct():
    assert bvid2aid(BVID) == AID


def test_comment_parser_preserves_images_note_metadata_and_thread_ids():
    raw = _comment(123)
    raw.update(
        {
            "root": 100,
            "parent": 101,
            "note_cvid": 18641039,
            "note_cvid_str": "18641039",
            "reply_control": {
                "is_note": True,
                "is_note_v2": True,
                "biz_scene": "note",
            },
        }
    )
    raw["content"] = {
        "message": "note preview...",
        "pictures": [
            {
                "img_src": "//i0.hdslb.com/bfs/note/example.jpg",
                "img_width": 1280,
                "img_height": 720,
                "img_size": 256.5,
            }
        ],
    }

    parsed = comment_service._parse_comment(raw).model_dump()

    assert parsed["root_rpid"] == 100
    assert parsed["parent_rpid"] == 101
    assert parsed["pictures"] == [
        {
            "url": "https://i0.hdslb.com/bfs/note/example.jpg",
            "width": 1280.0,
            "height": 720.0,
            "size_kb": 256.5,
        }
    ]
    assert parsed["note"] == {
        "cvid": "18641039",
        "summary": "note preview...",
        "images": ["https://i0.hdslb.com/bfs/note/example.jpg"],
        "url": "https://www.bilibili.com/read/cv18641039/?jump_opus=1",
        "content_is_preview": True,
    }


def test_comment_parser_preserves_long_plain_text_without_truncation():
    raw = _comment(456)
    long_text = "长评论" * 400
    raw["content"]["message"] = long_text

    parsed = comment_service._parse_comment(raw)

    assert parsed.content == long_text
    assert parsed.note is None


def test_comment_parser_supports_rich_text_note_metadata():
    raw = _comment(789)
    raw["content"] = {
        "message": "fallback preview",
        "rich_text": {
            "note": {
                "summary": "rich note summary",
                "images": ["//i0.hdslb.com/bfs/note/rich.jpg"],
                "click_url": "//www.bilibili.com/read/cv12345",
            }
        },
    }

    parsed = comment_service._parse_comment(raw)

    assert parsed.note is not None
    assert parsed.note.summary == "rich note summary"
    assert parsed.note.images == ["https://i0.hdslb.com/bfs/note/rich.jpg"]
    assert parsed.note.url == "https://www.bilibili.com/read/cv12345"


@pytest.mark.asyncio
async def test_article_comments_use_article_type_without_metadata_request(monkeypatch):
    calls = []

    async def fake_get_json(url, *, params, cred):
        calls.append((url, params, cred))
        return _main_response()

    class UnexpectedDynamic:
        def __init__(self, *args, **kwargs):
            raise AssertionError("legacy CV comments must not resolve dynamic metadata")

    monkeypatch.setattr(comment_service, "get_json", fake_get_json)
    monkeypatch.setattr(comment_service.dynamic, "Dynamic", UnexpectedDynamic)

    result = await comment_service.fetch_content_comments(
        content_type="article",
        content_id="18641039",
        cursor=None,
        limit=20,
        sort="hot",
        cred=None,
    )

    assert result["count"] == 1
    assert calls[0][1] == {
        "type": 12,
        "oid": 18641039,
        "mode": 3,
        "ps": 20,
    }


@pytest.mark.asyncio
async def test_dynamic_comments_resolve_comment_type_and_oid(monkeypatch):
    calls = []

    class FakeDynamic:
        def __init__(self, dynamic_id, credential):
            assert dynamic_id == 1211848387244064839
            assert credential is None

        async def get_info(self):
            return {
                "item": {
                    "basic": {
                        "comment_type": 17,
                        "rid_str": "1211848387244064839",
                    }
                }
            }

    async def fake_get_json(url, *, params, cred):
        calls.append((url, params, cred))
        return _main_response()

    monkeypatch.setattr(comment_service.dynamic, "Dynamic", FakeDynamic)
    monkeypatch.setattr(comment_service, "get_json", fake_get_json)

    result = await comment_service.fetch_content_comments(
        content_type="dynamic",
        content_id="1211848387244064839",
        cursor=None,
        limit=10,
        sort="time",
        cred=None,
    )

    assert result["count"] == 1
    assert calls[0][1] == {
        "type": 17,
        "oid": 1211848387244064839,
        "mode": 2,
        "ps": 10,
    }


@pytest.mark.asyncio
async def test_article_comment_replies_use_shared_reply_endpoint(monkeypatch):
    calls = []

    async def fake_get_json(url, *, params, cred):
        calls.append((url, params, cred))
        return _replies_response(2)

    monkeypatch.setattr(comment_service, "get_json", fake_get_json)

    result = await comment_service.fetch_content_comment_replies(
        content_type="article",
        content_id="18641039",
        root_rpid=7654321,
        page=1,
        limit=20,
        cred=None,
    )

    assert result["count"] == 2
    assert calls[0][0] == REPLIES_URL
    assert calls[0][1] == {
        "type": 12,
        "oid": 18641039,
        "root": 7654321,
        "ps": 20,
        "pn": 1,
    }
