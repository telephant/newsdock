"""A local test web server for the fetcher tests (no real site is ever contacted).

`LocalSite` serves chosen responses (status, body, headers, delay, gzip, redirects),
records every request, and listens on 127.0.0.1 on a free port. `tls_site` is the same
over TLS with a certificate for a chosen name signed by a throwaway authority
(`trustme`), plus a client context that trusts that authority.
"""

import gzip
import http.server
import socket
import ssl
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import pytest
import trustme


@dataclass
class Route:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str | None = "text/html; charset=utf-8"
    delay: float = 0.0
    gzip_body: bool = False
    announce_length: int | None = None  # a Content-Length that differs from the body


class LocalSite:
    def __init__(self, tls: trustme.LeafCert | None = None) -> None:
        self.routes: dict[str, Route] = {}
        self.requests: list[dict[str, object]] = []
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                site.requests.append(
                    {
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "time": time.monotonic(),
                    }
                )
                route = site.routes.get(self.path) or site.routes.get(
                    self.path.split("?", 1)[0]
                )
                if route is None:
                    route = Route(
                        status=404, body=b"not found", content_type="text/plain"
                    )
                if route.delay:
                    time.sleep(route.delay)
                body = gzip.compress(route.body) if route.gzip_body else route.body
                try:
                    self.send_response(route.status)
                    if route.content_type:
                        self.send_header("Content-Type", route.content_type)
                    for name, value in route.headers.items():
                        self.send_header(name, value)
                    if route.gzip_body:
                        self.send_header("Content-Encoding", "gzip")
                    length = (
                        route.announce_length
                        if route.announce_length is not None
                        else len(body)
                    )
                    self.send_header("Content-Length", str(length))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    pass  # the client stopped reading (a size cap) or refused the TLS

            def log_message(self, *args: object) -> None:
                pass

            def handle(self) -> None:
                try:
                    super().handle()
                except (ssl.SSLError, ConnectionError):
                    pass  # a failed handshake is a test outcome, not a server error

        self._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), Handler, bind_and_activate=False
        )
        self._server.daemon_threads = True
        self._server.allow_reuse_address = True
        self._server.server_bind()
        self._server.server_activate()
        self.port: int = self._server.server_address[1]
        if tls is not None:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            tls.configure_cert(context)
            self._server.socket = context.wrap_socket(
                self._server.socket, server_side=True, do_handshake_on_connect=False
            )
        # a short poll interval, so `shutdown()` does not wait half a second per server
        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.01), daemon=True
        )
        self._thread.start()

    def route(self, path: str, **kwargs: object) -> Route:
        route = Route(**kwargs)  # type: ignore[arg-type]
        self.routes[path] = route
        return route

    def hits(self, path: str) -> list[dict[str, object]]:
        return [r for r in self.requests if str(r["path"]).split("?", 1)[0] == path]

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture()
def site() -> Iterator[LocalSite]:
    local = LocalSite()
    try:
        yield local
    finally:
        local.close()


@pytest.fixture(scope="session")
def tls_authority() -> trustme.CA:
    return trustme.CA()


@pytest.fixture()
def tls_client_context(tls_authority: trustme.CA) -> ssl.SSLContext:
    context = ssl.create_default_context()
    tls_authority.configure_trust(context)
    return context


@pytest.fixture()
def tls_site_factory(
    tls_authority: trustme.CA,
) -> Iterator[Callable[[str], LocalSite]]:
    """`factory("site.test")` starts an HTTPS server certified for that name."""
    started: list[LocalSite] = []

    def make(name: str) -> LocalSite:
        local = LocalSite(tls=tls_authority.issue_cert(name))
        started.append(local)
        return local

    try:
        yield make
    finally:
        for local in started:
            local.close()


@pytest.fixture()
def make_site() -> Iterator[Callable[[], LocalSite]]:
    """A factory for more local servers in one test (for example a redirect target)."""
    started: list[LocalSite] = []

    def make() -> LocalSite:
        local = LocalSite()
        started.append(local)
        return local

    try:
        yield make
    finally:
        for local in started:
            local.close()


@pytest.fixture()
def unused_port() -> int:
    """A local port nothing is listening on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
