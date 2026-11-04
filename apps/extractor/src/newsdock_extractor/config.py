"""Settings for newsdock-extractor; the only place env vars are read (DR-9).

Every number is a setting with a code default (ADR-0013). Values marked provisional in
the spec (`docs/specs/body-extraction/spec.md` section 6) are measured, not decided; the
20,000-character text cap and the 7-day retention are decisions (D-3).
"""

from newsdock_config import LayeredSettings
from pydantic import field_validator
from pydantic_settings import SettingsConfigDict


class Settings(LayeredSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")
    section = "extractor"

    log_level: str = "INFO"
    heartbeat_file: str = "/tmp/healthy"
    # longer than one worst-case pass: total request timeout, robots fetch and a wait
    heartbeat_max_age_seconds: int = 300

    # the loop
    poll_interval_seconds: float = 5.0  # pause when nothing is due
    batch_size: int = 200  # pending rows read per pass (more than `concurrency`)
    concurrency: int = 16  # pages fetched at once (never two for one site)
    backfill_hours: int = 6  # first run only: articles of the last hours, no older
    retention_days: int = 7  # keep in step with sink.retention_days (D-3)
    db_backoff_seconds: float = 5.0  # wait after a failed pass, doubling up to the cap
    db_backoff_max_seconds: float = 60.0

    # politeness and safety (ADR-0035)
    user_agent: str = (
        "newsdock-extractor/0.1 (article text for a private news dock; "
        "respects robots.txt)"
    )
    per_host_delay_seconds: float = 5.0
    max_crawl_delay_seconds: float = 30.0  # a site asking for more is skipped
    robots_ttl_hours: int = 24
    robots_failure_minutes: int = 60
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 15.0
    total_timeout_seconds: float = 20.0
    max_bytes: int = 2_000_000
    max_redirects: int = 3
    max_attempts: int = 3  # for 429, 5xx, timeouts and connection errors
    retry_backoff_minutes: str = "5,30"  # delay before attempt 2, then attempt 3

    # extraction (domain)
    min_chars: int = 200  # shorter extracted text counts as `no_text`
    text_cap_chars: int = 20_000  # decision D-3
    passage_chars: int = 1000
    passage_max_chars: int = 1200

    @field_validator("retry_backoff_minutes")
    @classmethod
    def _check_backoff(cls, value: str) -> str:
        pieces = [piece.strip() for piece in value.split(",") if piece.strip()]
        if not pieces or not all(
            piece.isdigit() and int(piece) > 0 for piece in pieces
        ):
            raise ValueError("retry_backoff_minutes must be positive whole minutes")
        return ",".join(pieces)

    def retry_backoff(self) -> tuple[int, ...]:
        """The delays in minutes before the second, third, ... attempt."""
        return tuple(int(piece) for piece in self.retry_backoff_minutes.split(","))
