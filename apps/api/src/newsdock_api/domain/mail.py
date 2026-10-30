"""Sending mail: the port the domain uses (spec forgot-password, design C-44).

The domain only knows this interface; `adapters/smtp_mailer.py` speaks SMTP and tests
use a fake. `MailError` is the single failure and its text never contains the
recipient, the body or any credential, so it is safe to log.
"""

from typing import Protocol


class MailError(Exception):
    """The message could not be sent (connection, TLS, login, refusal, bad header)."""


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None:
        """Send one plain-text message or raise MailError."""
        ...
