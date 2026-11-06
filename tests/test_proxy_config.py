import pytest

from bili_stalker_mcp.config import _proxy_reachable, sanitize_proxy_url


def test_sanitize_proxy_url_masks_userinfo():
    assert (
        sanitize_proxy_url("http://user:secret@127.0.0.1:8080")
        == "http://***@127.0.0.1:8080"
    )
    assert sanitize_proxy_url("socks5://127.0.0.1:1080") == "socks5://127.0.0.1:1080"
    assert sanitize_proxy_url("") == ""


def test_proxy_reachable_probes_host_and_port(monkeypatch):
    probed: list[tuple[str, int]] = []

    class _FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_connect(address, timeout=None):
        probed.append(address)
        if address[1] == 50888:
            return _FakeSocket()
        raise OSError("refused")

    monkeypatch.setattr(
        "bili_stalker_mcp.config.socket.create_connection", _fake_connect
    )

    assert _proxy_reachable("http://127.0.0.1:50888") is True
    assert _proxy_reachable("http://127.0.0.1:9999") is False
    # https without explicit port probes 443, which the fake refuses.
    assert _proxy_reachable("https://proxy.example.com") is False
    assert probed == [
        ("127.0.0.1", 50888),
        ("127.0.0.1", 9999),
        ("proxy.example.com", 443),
    ]


def test_proxy_reachable_rejects_garbage_urls():
    assert _proxy_reachable("") is False
    assert _proxy_reachable("not a url") is False


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
    monkeypatch.setattr(config, "_active_proxy_url", "http://127.0.0.1:50888")

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
    monkeypatch.setattr(config, "_active_proxy_url", "")

    config.initialize_bilibili_request_settings()

    assert calls == []


@pytest.mark.parametrize("reachable", [True, False])
def test_proxy_resolution_is_cached(monkeypatch, reachable):
    from bili_stalker_mcp import config

    calls = []
    monkeypatch.setattr(config, "_active_proxy_url", None)
    monkeypatch.setattr(config, "PROXY_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(
        config, "_proxy_reachable", lambda url: calls.append(url) or reachable
    )
    expected = config.PROXY_URL if reachable else ""
    assert config.get_active_proxy_url() == expected
    assert config.get_active_proxy_url() == expected
    assert calls == [config.PROXY_URL]
