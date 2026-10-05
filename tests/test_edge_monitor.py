import unittest
from types import SimpleNamespace
from unittest.mock import call, patch
from threading import Event

from constants import GREENGRASS_IPC_SOCKET_ENV, SPOOL_PATH_ENV, USAGE_WARNING_THRESHOLD_PERCENT
from edge_monitor import MetricsCollector, run, _log_threshold_warnings


class FakeGpuCollector:
    def collect(self):
        return 42.0


class MetricsCollectorTests(unittest.TestCase):
    @patch("edge_monitor.psutil.disk_usage")
    @patch("edge_monitor.psutil.virtual_memory")
    @patch("edge_monitor.psutil.cpu_percent", return_value=37.5)
    def test_sample_contains_cpu_ram_disk_and_identity(self, cpu, memory, disk):
        memory.return_value = SimpleNamespace(used=100, total=200, percent=40.0)
        disk.return_value = SimpleNamespace(used=300, total=600, percent=70.0)

        collector = MetricsCollector(gpu_collector=FakeGpuCollector())
        sample = collector.collect()

        self.assertEqual(cpu.call_args_list, [call(interval=None), call(interval=None)])
        memory.assert_called_once_with()
        disk.assert_called_once_with("/")
        self.assertEqual(sample["cpu_usage_percent"], 37.5)
        self.assertEqual(sample["ram_usage_percent"], 40.0)
        self.assertEqual(sample["disk_usage_percent"], 70.0)
        self.assertEqual(sample["gpu_usage_percent"], 42.0)
        self.assertTrue(sample["sample_id"].startswith(sample["device_id"] + ":"))
        self.assertTrue(sample["device_id"])
        self.assertTrue(sample["timestamp"].endswith("+00:00"))

    @patch("edge_monitor.psutil.disk_usage")
    @patch("edge_monitor.psutil.virtual_memory")
    @patch("edge_monitor.psutil.cpu_percent", return_value=10.0)
    def test_unavailable_gpu_does_not_prevent_other_metrics(self, _cpu, memory, disk):
        memory.return_value = SimpleNamespace(used=1, total=2, percent=40.0)
        disk.return_value = SimpleNamespace(used=1, total=2, percent=70.0)

        class UnavailableGpuCollector:
            def collect(self):
                return None

        sample = MetricsCollector(gpu_collector=UnavailableGpuCollector()).collect()
        self.assertEqual(sample["cpu_usage_percent"], 10.0)
        self.assertEqual(sample["ram_usage_percent"], 40.0)
        self.assertEqual(sample["disk_usage_percent"], 70.0)
        self.assertIsNone(sample["gpu_usage_percent"])

    @patch("edge_monitor.psutil.cpu_percent", return_value=10.0)
    def test_primes_cpu_once_then_reads_non_blockingly(self, cpu):
        collector = MetricsCollector(gpu_collector=FakeGpuCollector())
        cpu.assert_called_once_with(interval=None)
        collector.collect()
        self.assertEqual(cpu.call_args_list, [call(interval=None), call(interval=None)])
    
    def test_run_uses_spool_path_from_environment(self):
        spool_path = "/tmp/test-edge-monitor/metrics.sqlite3"
        stop_event = Event()
        stop_event.set()

        with patch.dict(
            "edge_monitor.os.environ",
            {
                SPOOL_PATH_ENV: spool_path,
                GREENGRASS_IPC_SOCKET_ENV: "",
            },
        ), patch("edge_monitor.MetricsCollector"), patch(
            "edge_monitor.MetricsSpool"
        ) as spool_factory, patch(
            "edge_monitor.psutil.disk_usage"
        ), patch(
            "edge_monitor.Event", return_value=stop_event
        ), patch(
            "edge_monitor.signal.signal"
        ):
            self.assertEqual(run(), 0)

        spool_factory.assert_called_once_with(spool_path)
    
    @patch("edge_monitor.LOGGER.warning")
    def test_metrics_above_threshold_each_log_warning(self, warning):
        _log_threshold_warnings(
            {
                "device_id": "test-device",
                "cpu_usage_percent": 91.0,
                "ram_usage_percent": 92.0,
                "disk_usage_percent": 93.0,
                "gpu_usage_percent": 94.0,
            }
        )

        expected_message = "High %s usage on %s: %.1f%% (threshold: %.1f%%)"
        self.assertEqual(
            warning.call_args_list,
            [
                call(
                    expected_message,
                    "CPU",
                    "test-device",
                    91.0,
                    USAGE_WARNING_THRESHOLD_PERCENT,
                ),
                call(
                    expected_message,
                    "RAM",
                    "test-device",
                    92.0,
                    USAGE_WARNING_THRESHOLD_PERCENT,
                ),
                call(
                    expected_message,
                    "Disk",
                    "test-device",
                    93.0,
                    USAGE_WARNING_THRESHOLD_PERCENT,
                ),
                call(
                    expected_message,
                    "GPU",
                    "test-device",
                    94.0,
                    USAGE_WARNING_THRESHOLD_PERCENT,
                ),
            ],
        )

    @patch("edge_monitor.LOGGER.warning")
    def test_metrics_at_threshold_and_unavailable_gpu_do_not_warn(self, warning):
        _log_threshold_warnings(
            {
                "device_id": "test-device",
                "cpu_usage_percent": USAGE_WARNING_THRESHOLD_PERCENT,
                "ram_usage_percent": USAGE_WARNING_THRESHOLD_PERCENT,
                "disk_usage_percent": USAGE_WARNING_THRESHOLD_PERCENT,
                "gpu_usage_percent": None,
            }
        )

        warning.assert_not_called()

if __name__ == "__main__":
    unittest.main()
