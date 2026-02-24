import pytest

from bili_stalker_mcp import core


def _build_text_card(dynamic_id: str, content: str) -> dict:
    return {
        "desc": {
            "dynamic_id_str": dynamic_id,
            "timestamp": 1771601421,
            "type": 4,
        },
        "card": {
            "item": {"content": content},
        },
    }


@pytest.mark.asyncio
async def test_cursor_pagination_has_no_duplicates_or_missing(monkeypatch):
    pages = {
        0: {
            "cards": [
                _build_text_card("1", "a"),
                _build_text_card("2", "b"),
                _build_text_card("3", "c"),
            ],
            "has_more": True,
            "next_offset": "c2",
        },
        "c2": {
            "cards": [
                _build_text_card("4", "d"),
                _build_text_card("5", "e"),
            ],
            "has_more": False,
            "next_offset": None,
        },
    }

    class FakeUser:
        def __init__(self, uid, credential):
            self.uid = uid
            self.credential = credential

        async def get_dynamics(self, offset):
            return pages.get(offset, {"cards": [], "has_more": False, "next_offset": None})

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
