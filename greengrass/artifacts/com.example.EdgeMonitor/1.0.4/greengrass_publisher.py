"""Greengrass IPC publisher for the local metric spool."""

import json
import logging
import threading
from typing import Any, Dict

from constants import (
    IOT_TOPIC_TEMPLATE,
    PUBLISHER_IDLE_POLL_SECONDS,
    PUBLISH_RETRY_INITIAL_SECONDS,
    PUBLISH_RETRY_MAX_SECONDS,
    PUBLISH_TIMEOUT_SECONDS,
)
from metrics_spool import MetricsSpool

LOGGER = logging.getLogger("edge_monitor.publisher")


class GreengrassIpcPublisher:
    def __init__(self, timeout_seconds: float = PUBLISH_TIMEOUT_SECONDS):
        try:
            from awscrt.exceptions import AwsCrtError
            from awsiot.greengrasscoreipc.clientv2 import GreengrassCoreIPCClientV2
            from awsiot.greengrasscoreipc.model import (
                QOS,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Greengrass publishing requires awsiotsdk from requirements.txt"
            ) from exc

        try:
            self._client = GreengrassCoreIPCClientV2()
        except (AwsCrtError, KeyError, OSError, TimeoutError) as exc:
            raise RuntimeError("Could not connect to Greengrass IPC") from exc
        self._qos = QOS.AT_LEAST_ONCE
        self._timeout_seconds = timeout_seconds

    def publish(self, sample: Dict[str, Any]) -> None:
        device_id = sample.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            raise ValueError("metric sample requires a non-empty device_id")

        future = self._client.publish_to_iot_core_async(
            topic_name=IOT_TOPIC_TEMPLATE.format(device_id=device_id),
            qos=self._qos,
            payload=json.dumps(sample, separators=(",", ":")).encode("utf-8"),
        )
        future.result(timeout=self._timeout_seconds)

    def close(self) -> None:
        self._client.close()


class SpoolPublisherWorker(threading.Thread):
    def __init__(
        self,
        spool: MetricsSpool,
        publisher: GreengrassIpcPublisher,
        stop_event: threading.Event,
    ):
        super().__init__(name="greengrass-spool-publisher", daemon=True)
        self.spool = spool
        self.publisher = publisher
        self.stop_event = stop_event

    def run(self) -> None:
        retry_delay = PUBLISH_RETRY_INITIAL_SECONDS
        while not self.stop_event.is_set():
            try:
                item = self.spool.oldest()
                if item is None:
                    self.stop_event.wait(PUBLISHER_IDLE_POLL_SECONDS)
                    continue

                sequence, sample = item
                self.publisher.publish(sample)
                self.spool.acknowledge(sequence)
                retry_delay = PUBLISH_RETRY_INITIAL_SECONDS
            except Exception:
                LOGGER.exception(
                    "Greengrass publish failed; retaining queued sample and retrying "
                    "in %.1f seconds",
                    retry_delay,
                )
                self.stop_event.wait(retry_delay)
                retry_delay = min(retry_delay * 2, PUBLISH_RETRY_MAX_SECONDS)
