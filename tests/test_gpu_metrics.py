import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gpu_metrics import NvidiaGpuCollector


class NvidiaGpuCollectorTests(unittest.TestCase):
    @patch("gpu_metrics.subprocess.run")
    def test_collects_gpu_utilization_percent(self, run):
        run.return_value = SimpleNamespace(stdout="42\n")

        metrics = NvidiaGpuCollector().collect()

        self.assertEqual(metrics, 42.0)
        self.assertEqual(run.call_args.kwargs["timeout"], 2.0)
        self.assertEqual(
            run.call_args.args[0][1],
            "--query-gpu=utilization.gpu",
        )

    @patch("gpu_metrics.subprocess.run", side_effect=FileNotFoundError("nvidia-smi missing"))
    def test_missing_nvidia_smi_returns_null_values(self, _run):
        self.assertIsNone(NvidiaGpuCollector().collect())

    @patch("gpu_metrics.subprocess.run")
    def test_unsupported_readings_are_null(self, run):
        run.return_value = SimpleNamespace(stdout="N/A\n")
        self.assertIsNone(NvidiaGpuCollector().collect())

    @patch("gpu_metrics.subprocess.run")
    def test_empty_result_returns_null_utilization(self, run):
        run.return_value = SimpleNamespace(stdout="\n")
        self.assertIsNone(NvidiaGpuCollector().collect())


if __name__ == "__main__":
    unittest.main()
