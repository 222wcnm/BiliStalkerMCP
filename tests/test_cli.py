from bili_stalker_mcp import cli, server


class _FakeServer:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.transport: str | None = None

    def run(self, *, transport: str) -> None:
        self.transport = transport
        if self.error is not None:
            raise self.error


def test_main_returns_zero_after_normal_shutdown(monkeypatch):
    fake_server = _FakeServer()
    monkeypatch.setattr(server, "create_server", lambda: fake_server)
    monkeypatch.setattr(cli, "_configure_logging", lambda: None)
    monkeypatch.setattr(cli, "_close_http_client_sync", lambda: None)

    assert cli.main() == 0
    assert fake_server.transport == "stdio"


def test_main_returns_nonzero_when_server_start_fails(monkeypatch):
    fake_server = _FakeServer(error=RuntimeError("startup failed"))
    monkeypatch.setattr(server, "create_server", lambda: fake_server)
    monkeypatch.setattr(cli, "_configure_logging", lambda: None)
    monkeypatch.setattr(cli, "_close_http_client_sync", lambda: None)

    assert cli.main() == 1
