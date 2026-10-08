"""TC-20: heartbeat file carries its max age; the check compares file age to it."""

import http.server
import os
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from newsdock_config.health import check_heartbeat, check_http, write_heartbeat

NOW = 1_800_000_000.0


def age(path: Path, minutes: float) -> None:
    stamp = NOW - minutes * 60
    os.utime(path, (stamp, stamp))


def test_tc20_healthy_within_the_stored_max_age(tmp_path: Path) -> None:
    beat = tmp_path / "healthy"
    write_heartbeat(str(beat), 2400)
    age(beat, 25)
    assert check_heartbeat(str(beat), now=NOW) == 0


def test_tc20_unhealthy_past_the_stored_max_age(tmp_path: Path) -> None:
    beat = tmp_path / "healthy"
    write_heartbeat(str(beat), 2400)
    age(beat, 45)
    assert check_heartbeat(str(beat), now=NOW) == 1


def test_tc20_missing_file_is_unhealthy(tmp_path: Path) -> None:
    assert check_heartbeat(str(tmp_path / "nope"), now=NOW) == 1


@pytest.mark.parametrize("content", ["", "soon", "12.5x"])
def test_tc20_non_integer_content_is_unhealthy(tmp_path: Path, content: str) -> None:
    beat = tmp_path / "healthy"
    beat.write_text(content)
    assert check_heartbeat(str(beat), now=NOW - 0) == 1


def test_write_heartbeat_stores_the_number_and_refreshes_mtime(tmp_path: Path) -> None:
    beat = tmp_path / "healthy"
    write_heartbeat(str(beat), 120)
    assert beat.read_text().strip() == "120"
    old = 1_000_000.0
    os.utime(beat, (old, old))
    write_heartbeat(str(beat), 120)
    assert beat.stat().st_mtime > old  # rewritten, so the beat is fresh again


@pytest.fixture()
def server() -> Iterator[int]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200 if self.path == "/ok" else 503)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()


def test_check_http_200_is_healthy_and_503_is_not(server: int) -> None:
    assert check_http(f"http://127.0.0.1:{server}/ok", timeout_seconds=2) == 0
    assert check_http(f"http://127.0.0.1:{server}/bad", timeout_seconds=2) == 1


def test_check_http_connection_refused_is_unhealthy() -> None:
    assert check_http("http://127.0.0.1:9/ok", timeout_seconds=1) == 1
