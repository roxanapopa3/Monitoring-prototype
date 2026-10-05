"""Small SQLite-backed local history for collected metrics."""

import json
import logging
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from constants import (
    COUNT_SPOOL_SAMPLES_SQL,
    CREATE_SPOOL_TABLE_SQL,
    DELETE_OLDEST_SPOOL_SAMPLE_SQL,
    DELETE_SPOOL_SAMPLE_BY_SEQUENCE_SQL,
    DEFAULT_SPOOL_PATH,
    EXPIRE_SPOOL_SAMPLES_SQL,
    INSERT_SPOOL_SAMPLE_SQL,
    MAX_SAMPLE_AGE_SECONDS,
    MAX_SPOOLED_SAMPLES,
    SELECT_OLDEST_SPOOL_SAMPLE_SQL,
    SPOOL_SYNCHRONOUS_PRAGMA,
)

LOGGER = logging.getLogger("edge_monitor.spool")


class MetricsSpool:
    """Persist recent metric samples, retaining at most a count and age limit."""

    def __init__(
        self,
        path: str = DEFAULT_SPOOL_PATH,
        max_samples: int = MAX_SPOOLED_SAMPLES,
        max_age_seconds: int = MAX_SAMPLE_AGE_SECONDS,
    ):
        if max_samples < 1 or max_age_seconds < 1:
            raise ValueError("spool limits must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_samples = max_samples
        self.max_age_seconds = max_age_seconds
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute(SPOOL_SYNCHRONOUS_PRAGMA)
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(CREATE_SPOOL_TABLE_SQL)
        try:
            self.path.chmod(0o600)
        except OSError as exc:
            LOGGER.warning("Could not restrict spool database permissions: %s", exc)

    def _prune_expired(self, connection: sqlite3.Connection, now: float) -> int:
        cursor = connection.execute(
            EXPIRE_SPOOL_SAMPLES_SQL,
            (now - self.max_age_seconds,),
        )
        return cursor.rowcount

    def store(self, sample: Dict[str, Any]) -> int:
        """Commit one sample, expiring old records and evicting oldest on overflow."""
        payload = json.dumps(sample, separators=(",", ":"), ensure_ascii=True)
        now = time.time()
        with closing(self._connect()) as connection:
            with connection:
                self._prune_expired(connection, now)
                connection.execute(
                    INSERT_SPOOL_SAMPLE_SQL,
                    (now, payload),
                )
                dropped = 0
                while connection.execute(
                    COUNT_SPOOL_SAMPLES_SQL
                ).fetchone()[0] > self.max_samples:
                    connection.execute(DELETE_OLDEST_SPOOL_SAMPLE_SQL)
                    dropped += 1
        if dropped:
            LOGGER.warning("Spool full; evicted %d oldest sample(s)", dropped)
        return dropped

    def oldest(self) -> Optional[Tuple[int, Dict[str, Any]]]:
        """Return the oldest pending sample, without removing it."""
        now = time.time()
        with closing(self._connect()) as connection:
            with connection:
                self._prune_expired(connection, now)
                row = connection.execute(
                    SELECT_OLDEST_SPOOL_SAMPLE_SQL
                ).fetchone()
            if row is None:
                return None
            return int(row[0]), json.loads(row[1])

    def acknowledge(self, sequence: int) -> None:
        """Remove one sample after a future publisher confirms delivery."""
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    DELETE_SPOOL_SAMPLE_BY_SEQUENCE_SQL, (sequence,)
                )

    def count(self) -> int:
        with closing(self._connect()) as connection:
            with connection:
                self._prune_expired(connection, time.time())
                return int(
                    connection.execute(
                        COUNT_SPOOL_SAMPLES_SQL
                    ).fetchone()[0]
                )
