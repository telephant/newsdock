"""TC-20: the api healthcheck probes the configured port."""

import http.server
import threading
from collections.abc import Iterator

import pytest
from newsdock_api.adapters.healthcheck import main


@pytest.fixture()
def server() -> Iterator[int]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200 if self.path == "/api/health" else 404)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def test_healthy_when_the_configured_port_answers(
    server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEWSDOCK_CONFIG_FILE", raising=False)
    monkeypatch.setenv("NEWSDOCK_PORT", str(server))
    assert main() == 0


def test_unhealthy_when_nothing_listens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSDOCK_CONFIG_FILE", raising=False)
    monkeypatch.setenv("NEWSDOCK_PORT", "9")
    assert main() == 1
