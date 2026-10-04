"""Fixed configuration values and SQLite statements for the prototype."""

from pathlib import Path

DEFAULT_INTERVAL_SECONDS = 30.0
DEFAULT_DISK_PATH = "/"
NVIDIA_SMI_EXECUTABLE = "nvidia-smi"
DEFAULT_SPOOL_PATH = str(
    Path.home() / ".local" / "state" / "edge-monitor" / "metrics.sqlite3"
)
MAX_SPOOLED_SAMPLES = 10_000
MAX_SAMPLE_AGE_SECONDS = 7 * 24 * 60 * 60
GREENGRASS_IPC_SOCKET_ENV = "AWS_GG_NUCLEUS_DOMAIN_SOCKET_FILEPATH_FOR_COMPONENT"
IOT_TOPIC_TEMPLATE = "devices/{device_id}/metrics"
PUBLISH_TIMEOUT_SECONDS = 10.0
PUBLISH_RETRY_INITIAL_SECONDS = 1.0
PUBLISH_RETRY_MAX_SECONDS = 60.0
PUBLISHER_IDLE_POLL_SECONDS = 0.5

SPOOL_SYNCHRONOUS_PRAGMA = "PRAGMA synchronous=FULL"
CREATE_SPOOL_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS metric_samples (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        recorded_at REAL NOT NULL,
        payload TEXT NOT NULL
    )
"""
EXPIRE_SPOOL_SAMPLES_SQL = "DELETE FROM metric_samples WHERE recorded_at < ?"
INSERT_SPOOL_SAMPLE_SQL = (
    "INSERT INTO metric_samples(recorded_at, payload) VALUES (?, ?)"
)
COUNT_SPOOL_SAMPLES_SQL = "SELECT COUNT(*) FROM metric_samples"
DELETE_OLDEST_SPOOL_SAMPLE_SQL = (
    "DELETE FROM metric_samples WHERE sequence = "
    "(SELECT sequence FROM metric_samples ORDER BY sequence LIMIT 1)"
)
SELECT_OLDEST_SPOOL_SAMPLE_SQL = (
    "SELECT sequence, payload FROM metric_samples ORDER BY sequence LIMIT 1"
)
DELETE_SPOOL_SAMPLE_BY_SEQUENCE_SQL = (
    "DELETE FROM metric_samples WHERE sequence = ?"
)
