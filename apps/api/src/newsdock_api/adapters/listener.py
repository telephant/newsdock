"""Supervised Postgres LISTEN connection that wakes SSE streams (ADR-0018, C-18).

The trigger sends `articles_new` after every committed insert batch. The payload is
ignored: a notification only means "re-query". On every (re)connect the hub is woken
once, so nothing committed while the connection was down is waited for; the streams'
fallback poll covers the rest of an outage.
"""

import asyncio
import logging

import psycopg
from sqlalchemy.engine import make_url

from newsdock_api.domain.streams import WakeHub

logger = logging.getLogger(__name__)

CHANNEL = "articles_new"


def listen_dsn(database_url: str) -> str:
    """SQLAlchemy URL (`postgresql+psycopg://…`) to a libpq/psycopg conninfo URL."""
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


class NotifyListener:
    def __init__(
        self,
        dsn: str,
        hub: WakeHub,
        *,
        backoff: tuple[float, float] = (1.0, 30.0),
    ) -> None:
        self._dsn = dsn
        self._hub = hub
        self._first, self._max = backoff
        self.connected = asyncio.Event()  # set while LISTENing (tests and health)

    async def run(self) -> None:
        delay = self._first
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    self._dsn, autocommit=True
                ) as conn:
                    await conn.execute(f"LISTEN {CHANNEL}")
                    delay = self._first
                    self.connected.set()
                    self._hub.wake_all()  # catch up on anything missed while away
                    logger.info("listening on %s", CHANNEL)
                    async for _ in conn.notifies():
                        self._hub.wake_all()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — supervise: reconnect
                logger.warning("listener lost (%s); retrying in %.1fs", exc, delay)
            self.connected.clear()
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max)
