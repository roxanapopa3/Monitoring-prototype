import tempfile
import threading
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

from greengrass_publisher import GreengrassIpcPublisher, SpoolPublisherWorker
from metrics_spool import MetricsSpool


class GreengrassIpcPublisherTests(unittest.TestCase):
    @patch(
        "awsiot.greengrasscoreipc.clientv2.GreengrassCoreIPCClientV2",
        side_effect=KeyError("Greengrass IPC socket is not configured"),
    )
    def test_ipc_connection_startup_failure_is_reported(self, _client_type):
        with self.assertRaisesRegex(RuntimeError, "Could not connect to Greengrass IPC"):
            GreengrassIpcPublisher()

    @patch("awsiot.greengrasscoreipc.clientv2.GreengrassCoreIPCClientV2")
    def test_publishes_sample_as_qos_1_to_device_topic(self, client_type):
        client = client_type.return_value
        completed = Future()
        completed.set_result(None)
        client.publish_to_iot_core_async.return_value = completed

        publisher = GreengrassIpcPublisher(timeout_seconds=3.0)
        sample = {"device_id": "edge-1", "cpu_usage_percent": 20.0}
        publisher.publish(sample)

        publish_args = client.publish_to_iot_core_async.call_args.kwargs
        self.assertEqual(publish_args["topic_name"], "devices/edge-1/metrics")
        self.assertEqual(publish_args["qos"], "1")
        self.assertEqual(
            publish_args["payload"],
            b'{"device_id":"edge-1","cpu_usage_percent":20.0}',
        )
        publisher.close()
        client.close.assert_called_once_with()

    @patch("awsiot.greengrasscoreipc.clientv2.GreengrassCoreIPCClientV2")
    def test_publish_error_propagates_for_retry(self, client_type):
        client = client_type.return_value
        failed = Future()
        failed.set_exception(TimeoutError("IPC publish timed out"))
        client.publish_to_iot_core_async.return_value = failed
        publisher = GreengrassIpcPublisher()

        with self.assertRaises(TimeoutError):
            publisher.publish({"device_id": "edge-1"})

    @patch("awsiot.greengrasscoreipc.clientv2.GreengrassCoreIPCClientV2")
    def test_requires_device_id_for_topic(self, client_type):
        publisher = GreengrassIpcPublisher()
        with self.assertRaises(ValueError):
            publisher.publish({"cpu_usage_percent": 20.0})
        client_type.return_value.publish_to_iot_core_async.assert_not_called()


class SpoolPublisherWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.spool = MetricsSpool(
            str(Path(self.temp_dir.name) / "metrics.sqlite3"),
            max_samples=10,
            max_age_seconds=3600,
        )

    def test_publishes_oldest_then_acknowledges_only_successful_sample(self):
        self.spool.store({"device_id": "edge-1", "sample": 1})
        self.spool.store({"device_id": "edge-1", "sample": 2})
        stopped = threading.Event()

        class Publisher:
            def __init__(self):
                self.published = []

            def publish(self, sample):
                self.published.append(sample)
                if len(self.published) == 2:
                    stopped.set()

        publisher = Publisher()
        worker = SpoolPublisherWorker(self.spool, publisher, stopped)
        worker.start()
        worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual([sample["sample"] for sample in publisher.published], [1, 2])
        self.assertEqual(self.spool.count(), 0)

    def test_failed_publish_keeps_sample_in_spool(self):
        sample = {"device_id": "edge-1", "sample": 1}
        self.spool.store(sample)
        stopped = threading.Event()

        class FailingPublisher:
            def publish(self, _sample):
                stopped.set()
                raise RuntimeError("connection unavailable")

        worker = SpoolPublisherWorker(self.spool, FailingPublisher(), stopped)
        worker.start()
        worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(self.spool.count(), 1)
        self.assertEqual(self.spool.oldest()[1], sample)

if __name__ == "__main__":
    unittest.main()
