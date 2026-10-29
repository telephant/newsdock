"""TC-3 and TC-22 (AC-2, AC-14): the SMTP adapter, stub server and fake smtplib."""

import smtplib
import socketserver
import ssl
import threading
import time
from collections.abc import Callable, Iterator
from email import message_from_bytes
from email.message import EmailMessage
from typing import Any, Self

import pytest
from newsdock_api.adapters.smtp_mailer import SmtpMailer
from newsdock_api.domain.mail import MailError

ADDRESS = "ada@example.com"
PASSWORD = "smtp-password-for-tests"
BODY = "Your code is 123456.\n.A line that starts with a dot.\n"


# ---- a tiny SMTP server (plain, loopback): enough for smtplib.send_message ---------
class _Handler(socketserver.StreamRequestHandler):
    server: "StubSmtpServer"

    def _reply(self, text: str) -> None:
        self.wfile.write((text + "\r\n").encode())
        self.wfile.flush()

    def handle(self) -> None:
        record: dict[str, Any] = {
            "commands": [],
            "mail_from": None,
            "rcpt": [],
            "data": b"",
        }
        self._reply("220 stub ESMTP")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            text = line.decode().rstrip("\r\n")
            verb = text.split(" ", 1)[0].upper()
            record["commands"].append(verb)
            if verb == "EHLO":
                self._reply("250-stub")
                self._reply("250 8BITMIME")
            elif verb == "MAIL":
                record["mail_from"] = text.split(":", 1)[1].strip()
                self._reply("250 ok")
            elif verb == "RCPT":
                record["rcpt"].append(text.split(":", 1)[1].strip())
                self._reply("250 ok")
            elif verb == "DATA":
                self._reply("354 end with <CRLF>.<CRLF>")
                body = b""
                while True:
                    chunk = self.rfile.readline()
                    if chunk == b".\r\n":
                        break
                    body += chunk[1:] if chunk.startswith(b"..") else chunk
                record["data"] = body
                self._reply("250 queued")
            elif verb == "QUIT":
                self._reply("221 bye")
                self.server.sessions.append(record)
                return
            else:
                self._reply("502 not implemented")


class StubSmtpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.sessions: list[dict[str, Any]] = []

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def wait_for(self, count: int) -> None:
        deadline = time.time() + 5
        while len(self.sessions) < count and time.time() < deadline:
            time.sleep(0.02)


@pytest.fixture()
def stub() -> Iterator[StubSmtpServer]:
    server = StubSmtpServer()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


# ---- TC-3: a real message over the wire -------------------------------------------
def test_a_message_reaches_the_server_with_headers_and_body_intact(
    stub: StubSmtpServer,
) -> None:
    mailer = SmtpMailer(
        host="127.0.0.1", port=stub.port, security="none", user="", password=None,
        sender="noreply@example.test", timeout=5,
    )  # fmt: skip
    mailer.send(ADDRESS, "newsdock: your password reset code", BODY)
    stub.wait_for(1)
    (session,) = stub.sessions
    assert session["commands"] == ["EHLO", "MAIL", "RCPT", "DATA", "QUIT"]
    assert session["mail_from"] == "<noreply@example.test>"
    assert session["rcpt"] == [f"<{ADDRESS}>"]
    parsed = message_from_bytes(session["data"])
    assert parsed["From"] == "noreply@example.test"
    assert parsed["To"] == ADDRESS
    assert parsed["Subject"] == "newsdock: your password reset code"
    assert parsed["Auto-Submitted"] == "auto-generated"
    payload = parsed.get_payload(decode=True)
    assert isinstance(payload, bytes)
    assert payload.decode().replace("\r\n", "\n") == BODY


def test_two_sends_in_a_row_both_arrive(stub: StubSmtpServer) -> None:
    mailer = SmtpMailer(
        host="127.0.0.1", port=stub.port, security="none", user="", password=None,
        sender="noreply@example.test", timeout=5,
    )  # fmt: skip
    mailer.send("a@example.com", "s", "one\n")
    mailer.send("b@example.com", "s", "two\n")
    stub.wait_for(2)
    assert [s["rcpt"] for s in stub.sessions] == [
        ["<a@example.com>"],
        ["<b@example.com>"],
    ]


def test_a_refused_connection_becomes_a_mail_error() -> None:
    mailer = SmtpMailer(
        host="127.0.0.1", port=1, security="none", user="", password=None,
        sender="noreply@example.test", timeout=2,
    )  # fmt: skip
    with pytest.raises(MailError):
        mailer.send(ADDRESS, "s", BODY)


# ---- TC-22: TLS rules and error mapping with a fake smtplib ------------------------
class FakeSmtp:
    """Records the calls a real smtplib connection would receive."""

    def __init__(self, calls: list[str], fail_on: dict[str, Exception]) -> None:
        self._calls = calls
        self._fail_on = fail_on
        self.sent: list[EmailMessage] = []
        self.context: ssl.SSLContext | None = None

    def _do(self, name: str) -> None:
        self._calls.append(name)
        if name in self._fail_on:
            raise self._fail_on[name]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self._calls.append("quit")

    def starttls(self, *, context: ssl.SSLContext | None = None) -> None:
        self.context = context
        self._do("starttls")

    def ehlo(self) -> None:
        self._do("ehlo")

    def login(self, user: str, password: str) -> None:
        self._calls.append(f"login:{user}")
        if "login" in self._fail_on:
            raise self._fail_on["login"]

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)
        self._do("send_message")


class Factories:
    def __init__(self, fail_on: dict[str, Exception] | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on or {}
        self.last: FakeSmtp | None = None
        self.args: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _make(self, kind: str) -> Callable[..., FakeSmtp]:
        def factory(*args: Any, **kwargs: Any) -> FakeSmtp:
            self.calls.append(f"connect:{kind}")
            self.args.append((kind, args, kwargs))
            if "connect" in self.fail_on:
                raise self.fail_on["connect"]
            self.last = FakeSmtp(self.calls, self.fail_on)
            return self.last

        return factory

    @property
    def plain(self) -> Callable[..., FakeSmtp]:
        return self._make("smtp")

    @property
    def ssl(self) -> Callable[..., FakeSmtp]:
        return self._make("smtp_ssl")


def mailer(f: Factories, **overrides: Any) -> SmtpMailer:
    settings: dict[str, Any] = dict(
        host="smtp.example.test", port=587, security="starttls",
        user="login@example.test", password=PASSWORD,
        sender="noreply@example.test", timeout=10,
    )  # fmt: skip
    settings.update(overrides)
    return SmtpMailer(**settings, smtp_factory=f.plain, smtp_ssl_factory=f.ssl)


def test_starttls_comes_before_ehlo_before_login_before_sending() -> None:
    f = Factories()
    mailer(f).send(ADDRESS, "s", BODY)
    assert f.calls == [
        "connect:smtp", "starttls", "ehlo", "login:login@example.test",
        "send_message", "quit",
    ]  # fmt: skip
    kind, args, kwargs = f.args[0]
    assert args == ("smtp.example.test", 587) and kwargs["timeout"] == 10


def test_starttls_uses_a_verifying_tls_context() -> None:
    f = Factories()
    mailer(f).send(ADDRESS, "s", BODY)
    assert f.last is not None and f.last.context is not None
    assert f.last.context.verify_mode == ssl.CERT_REQUIRED
    assert f.last.context.check_hostname is True


def test_ssl_mode_uses_implicit_tls_and_never_starttls() -> None:
    f = Factories()
    mailer(f, security="ssl", port=465).send(ADDRESS, "s", BODY)
    assert f.calls == [
        "connect:smtp_ssl",
        "login:login@example.test",
        "send_message",
        "quit",
    ]
    kind, args, kwargs = f.args[0]
    assert args == ("smtp.example.test", 465) and kwargs["timeout"] == 10
    assert isinstance(kwargs["context"], ssl.SSLContext)


def test_no_login_when_no_user_is_configured() -> None:
    f = Factories()
    mailer(f, user="", password=None).send(ADDRESS, "s", BODY)
    assert not any(c.startswith("login") for c in f.calls)
    assert f.calls[:3] == ["connect:smtp", "starttls", "ehlo"]


def test_none_security_is_plain_and_only_for_loopback_hosts() -> None:
    f = Factories()
    mailer(f, security="none", host="localhost", port=25, user="", password=None).send(
        ADDRESS, "s", BODY
    )
    assert f.calls == ["connect:smtp", "send_message", "quit"]
    for host in ("smtp.example.test", "10.0.0.5", "mail.localhost.evil.test"):
        with pytest.raises(ValueError, match="loopback"):
            mailer(Factories(), security="none", host=host, user="", password=None)


def test_credentials_are_never_sent_over_plain_smtp() -> None:
    with pytest.raises(ValueError, match="plain"):
        mailer(Factories(), security="none", host="localhost")  # user + password given


def test_an_unknown_security_value_is_refused() -> None:
    with pytest.raises(ValueError, match="security"):
        mailer(Factories(), security="tls")


def test_the_message_has_the_expected_headers_and_body() -> None:
    f = Factories()
    mailer(f).send(ADDRESS, "newsdock: your password reset code", BODY)
    assert f.last is not None
    (message,) = f.last.sent
    assert message["From"] == "noreply@example.test"
    assert message["To"] == ADDRESS
    assert message["Subject"] == "newsdock: your password reset code"
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["Bcc"] is None
    assert message.get_content() == BODY


FAILURES = [
    ("connect", ConnectionRefusedError(f"cannot reach {ADDRESS}")),
    ("connect", TimeoutError("timed out")),
    ("starttls", smtplib.SMTPNotSupportedError("STARTTLS extension not supported")),
    ("starttls", ssl.SSLError("certificate verify failed")),
    (
        "login",
        smtplib.SMTPAuthenticationError(535, f"bad password {PASSWORD}".encode()),
    ),
    ("send_message", smtplib.SMTPRecipientsRefused({ADDRESS: (550, b"no such user")})),
    ("send_message", smtplib.SMTPDataError(554, b"rejected 123456")),
    ("send_message", smtplib.SMTPServerDisconnected("Connection unexpectedly closed")),
]


@pytest.mark.parametrize("where,error", FAILURES)
def test_every_failure_becomes_a_mail_error_that_leaks_nothing(
    where: str, error: Exception
) -> None:
    f = Factories(fail_on={where: error})
    with pytest.raises(MailError) as caught:
        mailer(f).send(ADDRESS, "s", BODY)
    text = str(caught.value)
    assert text == f"mail send failed: {type(error).__name__}"
    for secret in (ADDRESS, PASSWORD, "123456", "login@example.test"):
        assert secret not in text
    assert caught.value.__cause__ is None  # `from None`: no chained text in tracebacks


def test_a_value_error_from_the_message_builder_is_also_a_mail_error() -> None:
    f = Factories()
    with pytest.raises(MailError):
        mailer(f).send("ada@example.com\r\nBcc: evil@example.com", "s", BODY)
    assert f.calls == []  # nothing was sent
