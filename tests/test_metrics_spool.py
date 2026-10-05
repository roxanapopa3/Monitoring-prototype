import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from metrics_spool import MetricsSpool


class MetricsSpoolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = str(Path(self.temp_dir.name) / "metrics.sqlite3")

    def test_samples_survive_reopening_the_spool(self):
        spool = MetricsSpool(self.database_path, max_samples=5, max_age_seconds=3600)
        sample = {"sample_id": "sample-1", "cpu_usage_percent": 25.0}
        self.assertEqual(spool.store(sample), 0)

        reopened_spool = MetricsSpool(
            self.database_path, max_samples=5, max_age_seconds=3600
        )
        self.assertEqual(reopened_spool.oldest()[1], sample)

    def test_count_limit_discards_oldest_sample(self):
        spool = MetricsSpool(self.database_path, max_samples=2, max_age_seconds=3600)
        spool.store({"sample_id": "first"})
        spool.store({"sample_id": "second"})

        dropped = spool.store({"sample_id": "third"})

        self.assertEqual(dropped, 1)
        self.assertEqual(spool.count(), 2)
        self.assertEqual(spool.oldest()[1]["sample_id"], "second")

    def test_old_samples_expire_when_reading_oldest(self):
        spool = MetricsSpool(self.database_path, max_samples=5, max_age_seconds=60)
        with patch("metrics_spool.time.time", return_value=1000):
            spool.store({"sample_id": "expired"})

        with patch("metrics_spool.time.time", return_value=1061):
            self.assertIsNone(spool.oldest())

    def test_old_samples_expire_when_counting(self):
        spool = MetricsSpool(self.database_path, max_samples=5, max_age_seconds=60)
        with patch("metrics_spool.time.time", return_value=1000):
            spool.store({"sample_id": "expired"})

        with patch("metrics_spool.time.time", return_value=1061):
            self.assertEqual(spool.count(), 0)

    def test_acknowledgement_removes_sample(self):
        spool = MetricsSpool(self.database_path, max_samples=5, max_age_seconds=3600)
        spool.store({"sample_id": "sample-1"})
        sequence, _sample = spool.oldest()

        spool.acknowledge(sequence)

        self.assertEqual(spool.count(), 0)


if __name__ == "__main__":
    unittest.main()
