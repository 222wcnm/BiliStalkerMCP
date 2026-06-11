import pytest

from bili_stalker_mcp import core
from bili_stalker_mcp.observability import begin_request, snapshot_metrics


def _build_text_card(dynamic_id: str, content: str) -> dict:
    return {
        "id_str": dynamic_id,
        "type": "DYNAMIC_TYPE_WORD",
        "modules": {
            "module_author": {"pub_ts": "1771601421"},
            "module_dynamic": {
                "desc": {"text": content},
                "major": None,
            },
            "module_stat": {
                "like": {"count": 0},
                "comment": {"count": 0},
                "forward": {"count": 0},
            },
        },
    }


@pytest.mark.asyncio
async def test_cursor_pagination_has_no_duplicates_or_missing(monkeypatch):
    pages = {
        "": {
            "items": [
                _build_text_card("1", "a"),
                _build_text_card("2", "b"),
                _build_text_card("3", "c"),
            ],
            "has_more": True,
            "offset": "c2",
        },
        "c2": {
            "items": [
                _build_text_card("4", "d"),
                _build_text_card("5", "e"),
            ],
            "has_more": False,
            "offset": "",
        },
    }

    class FakeUser:
        def __init__(self, uid, credential):
            self.uid = uid
            self.credential = credential

        async def get_dynamics_new(self, offset):
            return pages.get(offset, {"items": [], "has_more": False, "offset": ""})

    monkeypatch.setattr(core.user, "User", FakeUser)

    first = await core.fetch_user_dynamics(
        user_id=1,
        offset=0,
        limit=2,
        cred=object(),
        dynamic_type="TEXT",
    )
    second = await core.fetch_user_dynamics(
        user_id=1,
        offset=0,
        limit=2,
        cred=object(),
        dynamic_type="TEXT",
        cursor=first["next_cursor"],
    )
    third = await core.fetch_user_dynamics(
        user_id=1,
        offset=0,
        limit=2,
        cred=object(),
        dynamic_type="TEXT",
        cursor=second["next_cursor"],
    )

    ids = [item["dynamic_id"] for item in first["dynamics"] + second["dynamics"] + third["dynamics"]]

    assert first["has_more"] is True
    assert second["has_more"] is True
    assert third["has_more"] is False
    assert ids == ["1", "2", "3", "4", "5"]
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_cursor_and_offset_cannot_be_combined():
    token = core._encode_cursor_token(
        api_cursor=0,
        skip_matches=0,
        user_id=1,
        dynamic_type="TEXT",
    )

    with pytest.raises(ValueError, match="cannot be combined"):
        await core.fetch_user_dynamics(
            user_id=1,
            offset=1,
            limit=1,
            cred=object(),
            dynamic_type="TEXT",
            cursor=token,
        )


@pytest.mark.asyncio
async def test_dynamic_lazy_pause_triggers_between_batches(monkeypatch):
    def build_page(start_id: int, count: int, next_offset: str | None, has_more: bool) -> dict:
        cards = [
            _build_text_card(str(dynamic_id), f"content-{dynamic_id}")
            for dynamic_id in range(start_id, start_id + count)
        ]
        return {
            "items": cards,
            "has_more": has_more,
            "offset": next_offset or "",
        }

    pages = {
        "": build_page(1, 30, "c2", True),
        "c2": build_page(31, 30, "c3", True),
        "c3": build_page(61, 5, None, False),
    }
    sleep_calls = []

    class FakeUser:
        def __init__(self, uid, credential):
            self.uid = uid
            self.credential = credential

        async def get_dynamics_new(self, offset):
            return pages[offset]

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(core.user, "User", FakeUser)
    monkeypatch.setattr("bili_stalker_mcp.services.dynamic_service.LAZY_ENABLED", True)
    monkeypatch.setattr("bili_stalker_mcp.services.dynamic_service.LAZY_DYNAMICS_BATCH", 30)
    monkeypatch.setattr("bili_stalker_mcp.services.dynamic_service.LAZY_SLEEP_MIN_SECONDS", 5)
    monkeypatch.setattr("bili_stalker_mcp.services.dynamic_service.LAZY_SLEEP_MAX_SECONDS", 5)
    monkeypatch.setattr("bili_stalker_mcp.services.dynamic_service.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MIN_MS", 0)
    monkeypatch.setattr("bili_stalker_mcp.infra.upstream.REQUEST_JITTER_MAX_MS", 0)
    begin_request("dynamic-lazy")

    result = await core.fetch_user_dynamics(
        user_id=1,
        offset=0,
        limit=65,
        cred=object(),
        dynamic_type="TEXT",
    )

    metrics = snapshot_metrics()

    assert result["total_fetched"] == 65
    assert result["has_more"] is False
    assert sleep_calls == [5, 5]
    assert metrics["lazy_pause_count"] == 2
    assert metrics["lazy_pause_ms"] == 10000.0
