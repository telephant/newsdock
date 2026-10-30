"""SMTP mailer (role: outbound mail): standard library only, provider = settings.

Three transports (ADR-0027): `starttls` (plain connect, upgrade, then log in),
`ssl` (implicit TLS, usually port 465) and `none` (plain, loopback hosts only, never
with credentials). Every failure is raised as `MailError` carrying just the exception
class name and `from None`, because smtplib errors can contain the recipient or server
replies and tracebacks get logged.
"""

import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

from newsdock_api.domain.mail import MailError

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SECURITY_MODES = ("starttls", "ssl", "none")


class SmtpMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        security: str,
        user: str,
        password: str | None,
        sender: str,
        timeout: float,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
        smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL,
    ) -> None:
        if security not in SECURITY_MODES:
            raise ValueError(
                f"smtp security must be one of {', '.join(SECURITY_MODES)}"
            )
        if security == "none":
            if host not in LOOPBACK_HOSTS:
                raise ValueError(
                    "smtp security 'none' is only allowed for loopback hosts"
                )
            if user or password:
                raise ValueError("credentials are never sent over plain SMTP")
        self._host = host
        self._port = port
        self._security = security
        self._user = user
        self._password = password or ""
        self._sender = sender
        self._timeout = timeout
        self._smtp = smtp_factory
        self._smtp_ssl = smtp_ssl_factory

    def send(self, to: str, subject: str, body: str) -> None:
        try:
            message = self._build(to, subject, body)
            self._deliver(message)
        except (OSError, ValueError) as exc:
            # OSError covers SMTPException, TLS and timeouts; ValueError a bad header
            raise MailError(f"mail send failed: {type(exc).__name__}") from None

    def _build(self, to: str, subject: str, body: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(body)
        return message

    def _deliver(self, message: EmailMessage) -> None:
        if self._security == "ssl":
            context = ssl.create_default_context()
            with self._smtp_ssl(
                self._host, self._port, timeout=self._timeout, context=context
            ) as smtp:
                self._login(smtp)
                smtp.send_message(message)
        elif self._security == "starttls":
            context = ssl.create_default_context()
            with self._smtp(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.starttls(context=context)
                smtp.ehlo()  # identify again over the encrypted channel
                self._login(smtp)
                smtp.send_message(message)
        else:
            with self._smtp(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.send_message(message)

    def _login(self, smtp: Any) -> None:
        if self._user:
            smtp.login(self._user, self._password)
