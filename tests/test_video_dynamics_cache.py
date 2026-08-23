import pytest

from bili_stalker_mcp import core
from bili_stalker_mcp.services import dynamic_service, user_service
from bili_stalker_mcp.services.user_service import fetch_user_videos


@pytest.fixture(autouse=True)
def _clean_caches():
    user_service._fetch_user_videos_cached.cache_clear()
    dynamic_service._fetch_user_dynamics_cached.cache_clear()
    yield
    user_service._fetch_user_videos_cached.cache_clear()
    dynamic_service._fetch_user_dynamics_cached.cache_clear()


def _empty_videos_payload() -> dict:
    return {"list": {"vlist": []}, "page": {"count": 0}}


def _text_dynamic_page(next_offset: str = "", has_more: bool = False) -> dict:
    return {
        "items": [
            {
                "id_str": "1",
                "type": "DYNAMIC_TYPE_WORD",
                "modules": {
                    "module_author": {"pub_ts": "1771601421"},
                    "module_dynamic": {"desc": {"text": "hi"}, "major": None},
                    "module_stat": {
                        "like": {"count": 0},
                        "comment": {"count": 0},
                        "forward": {"count": 0},
                    },
                },
            }
        ],
        "has_more": has_more,
        "offset": next_offset,
    }


def _make_video_user(instances, keyword_calls=None):
    class FakeUser:
        def __init__(self, uid, credential):
            self.uid = uid
            self.credential = credential
            self.videos_calls = 0
            instances.append(self)

        async def get_videos(self, pn, ps, keyword=""):
            self.videos_calls += 1
            if keyword_calls is not None:
                keyword_calls.append(keyword)
            return _empty_videos_payload()

    return FakeUser


def _make_dynamics_user(instances, next_offset="", has_more=False):
    class FakeUser:
        def __init__(self, uid, credential):
            self.uid = uid
            self.credential = credential
            self.dynamics_calls = 0
            instances.append(self)

        async def get_dynamics_new(self, offset):
            self.dynamics_calls += 1
            return _text_dynamic_page(next_offset=next_offset, has_more=has_more)

    return FakeUser


@pytest.mark.asyncio
async def test_fetch_user_videos_serves_repeat_calls_from_cache(monkeypatch):
    instances: list = []
    monkeypatch.setattr(core.user, "User", _make_video_user(instances))
    cred = object()

    first = await fetch_user_videos(user_id=1, page=1, limit=5, cred=cred)
    second = await fetch_user_videos(user_id=1, page=1, limit=5, cred=cred)

    assert first == second
    assert [u.videos_calls for u in instances] == [1]
    assert user_service._fetch_user_videos_cached.cache_info().hits >= 1


@pytest.mark.asyncio
async def test_fetch_user_videos_cache_key_includes_keyword(monkeypatch):
    instances: list = []
    keyword_calls: list = []
    monkeypatch.setattr(core.user, "User", _make_video_user(instances, keyword_calls))
    cred = object()

    await fetch_user_videos(user_id=1, page=1, limit=5, cred=cred, keyword="a")
    await fetch_user_videos(user_id=1, page=1, limit=5, cred=cred, keyword="b")

    assert [u.videos_calls for u in instances] == [1, 1]
    assert keyword_calls == ["a", "b"]


@pytest.mark.asyncio
async def test_fetch_user_dynamics_serves_repeat_calls_from_cache(monkeypatch):
    instances: list = []
    monkeypatch.setattr(core.user, "User", _make_dynamics_user(instances))
    cred = object()

    first = await core.fetch_user_dynamics(
        user_id=1, limit=3, cred=cred, dynamic_type="TEXT"
    )
    second = await core.fetch_user_dynamics(
        user_id=1, limit=3, cred=cred, dynamic_type="TEXT"
    )

    assert first == second
    assert [u.dynamics_calls for u in instances] == [1]
    assert dynamic_service._fetch_user_dynamics_cached.cache_info().hits >= 1


@pytest.mark.asyncio
async def test_fetch_user_dynamics_offset_bypasses_cache(monkeypatch):
    instances: list = []
    monkeypatch.setattr(core.user, "User", _make_dynamics_user(instances))
    cred = object()

    await core.fetch_user_dynamics(
        user_id=1, limit=3, cred=cred, dynamic_type="TEXT", offset=0
    )
    await core.fetch_user_dynamics(
        user_id=1, limit=3, cred=cred, dynamic_type="TEXT", offset=0
    )

    assert [u.dynamics_calls for u in instances] == [1, 1]
    assert dynamic_service._fetch_user_dynamics_cached.cache_info().currsize == 0


@pytest.mark.asyncio
async def test_fetch_user_dynamics_cache_key_includes_cursor(monkeypatch):
    instances: list = []
    monkeypatch.setattr(
        core.user,
        "User",
        _make_dynamics_user(instances, next_offset="5", has_more=True),
    )
    cred = object()

    first = await core.fetch_user_dynamics(
        user_id=1, limit=1, cred=cred, dynamic_type="TEXT"
    )
    await core.fetch_user_dynamics(
        user_id=1,
        limit=1,
        cred=cred,
        dynamic_type="TEXT",
        cursor=first["next_cursor"],
    )

    assert first["next_cursor"] is not None
    assert [u.dynamics_calls for u in instances] == [1, 1]
