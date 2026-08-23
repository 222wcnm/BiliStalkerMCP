import pytest


@pytest.fixture()
def _reset_initialized(monkeypatch):
    from bili_stalker_mcp import config

    monkeypatch.setattr(config, "_request_settings_initialized", False)
    yield
    monkeypatch.setattr(config, "_request_settings_initialized", True)


def test_initialize_applies_explicit_proxy_to_bilibili_api(
    monkeypatch, _reset_initialized
):
    import bilibili_api

    from bili_stalker_mcp import config

    calls: list[str] = []
    monkeypatch.setattr(
        bilibili_api.request_settings,
        "set_proxy",
        lambda proxy: calls.append(proxy),
        raising=False,
    )
    monkeypatch.setattr(config, "PROXY_URL", "http://127.0.0.1:50888")

    config.initialize_bilibili_request_settings()

    assert calls == ["http://127.0.0.1:50888"]


def test_initialize_skips_proxy_when_unset(monkeypatch, _reset_initialized):
    import bilibili_api

    from bili_stalker_mcp import config

    calls: list[str] = []
    monkeypatch.setattr(
        bilibili_api.request_settings,
        "set_proxy",
        lambda proxy: calls.append(proxy),
        raising=False,
    )
    monkeypatch.setattr(config, "PROXY_URL", "")

    config.initialize_bilibili_request_settings()

    assert calls == []
