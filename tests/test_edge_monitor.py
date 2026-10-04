import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from edge_monitor import MetricsCollector


class FakeGpuCollector:
    def collect(self):
        return 42.0


class MetricsCollectorTests(unittest.TestCase):
    @patch("edge_monitor.psutil.disk_usage")
    @patch("edge_monitor.psutil.virtual_memory")
    @patch("edge_monitor.psutil.cpu_percent", return_value=37.5)
    def test_sample_contains_cpu_ram_disk_and_identity(self, cpu, memory, disk):
        memory.return_value = SimpleNamespace(used=100, total=200, percent=50.0)
        disk.return_value = SimpleNamespace(used=300, total=600, percent=50.0)

        collector = MetricsCollector(gpu_collector=FakeGpuCollector())
        sample = collector.collect()

        self.assertEqual(cpu.call_args_list, [call(interval=None), call(interval=None)])
        memory.assert_called_once_with()
        disk.assert_called_once_with("/")
        self.assertEqual(sample["cpu_usage_percent"], 37.5)
        self.assertEqual(sample["ram_usage_percent"], 50.0)
        self.assertEqual(sample["disk_usage_percent"], 50.0)
        self.assertEqual(sample["gpu_usage_percent"], 42.0)
        self.assertNotIn("ram_used_bytes", sample)
        self.assertNotIn("ram_total_bytes", sample)
        self.assertNotIn("disk_used_bytes", sample)
        self.assertNotIn("disk_total_bytes", sample)
        self.assertTrue(sample["sample_id"].startswith(sample["device_id"] + ":"))
        self.assertTrue(sample["device_id"])
        self.assertTrue(sample["timestamp"].endswith("+00:00"))

    @patch("edge_monitor.psutil.disk_usage")
    @patch("edge_monitor.psutil.virtual_memory")
    @patch("edge_monitor.psutil.cpu_percent", return_value=10.0)
    def test_unavailable_gpu_does_not_prevent_other_metrics(self, _cpu, memory, disk):
        memory.return_value = SimpleNamespace(used=1, total=2, percent=50.0)
        disk.return_value = SimpleNamespace(used=1, total=2, percent=50.0)

        class UnavailableGpuCollector:
            def collect(self):
                return None

        sample = MetricsCollector(gpu_collector=UnavailableGpuCollector()).collect()
        self.assertEqual(sample["cpu_usage_percent"], 10.0)
        self.assertEqual(sample["ram_usage_percent"], 50.0)
        self.assertEqual(sample["disk_usage_percent"], 50.0)
        self.assertIsNone(sample["gpu_usage_percent"])

    @patch("edge_monitor.psutil.cpu_percent", return_value=10.0)
    def test_primes_cpu_once_then_reads_non_blockingly(self, cpu):
        collector = MetricsCollector(gpu_collector=FakeGpuCollector())
        cpu.assert_called_once_with(interval=None)
        collector.collect()
        self.assertEqual(cpu.call_args_list, [call(interval=None), call(interval=None)])

if __name__ == "__main__":
    unittest.main()
