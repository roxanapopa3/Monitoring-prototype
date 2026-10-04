#!/usr/bin/env python3
"""Periodically collect CPU, memory, and disk usage on a Linux device."""

import json
import logging
import os
import signal
import socket
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from functools import partial
from threading import Event
from typing import Any, Dict, Optional, Protocol

import psutil

from constants import (
    DEFAULT_DISK_PATH,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_SPOOL_PATH,
    GREENGRASS_IPC_SOCKET_ENV,
    PUBLISH_TIMEOUT_SECONDS,
    SPOOL_PATH_ENV,
    CPU_WARNING_THRESHOLD_PERCENT,
)
from gpu_metrics import NvidiaGpuCollector
from greengrass_publisher import GreengrassIpcPublisher, SpoolPublisherWorker
from metrics_spool import MetricsSpool

LOGGER = logging.getLogger("edge_monitor")


class GpuCollector(Protocol):
    def collect(self) -> Optional[float]:
        pass


class MetricsCollector:
    def __init__(
        self,
        disk_path: str = DEFAULT_DISK_PATH,
        gpu_collector: Optional[GpuCollector] = None,
    ):
        self.disk_path = disk_path
        self.device_id = socket.gethostname()
        self.gpu_collector = gpu_collector or NvidiaGpuCollector()
        # Prime psutil's non-blocking CPU sampler; the first reading is discarded.
        psutil.cpu_percent(interval=None)

    def collect(self) -> Dict[str, Any]:
        """Collect one sample without waiting for a CPU sampling interval."""
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(self.disk_path)
        return {
            "sample_id": "{}:{}".format(self.device_id, uuid.uuid4().hex),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_id": self.device_id,
            "cpu_usage_percent": cpu_percent,
            "ram_usage_percent": memory.percent,
            "disk_usage_percent": disk.percent,
            "gpu_usage_percent": self.gpu_collector.collect(),
        }


def _request_stop(stop_event: Event, _signum: int, _frame: Any) -> None:
    stop_event.set()

def _log_threshold_warnings(sample: Dict[str, Any]) -> None:
    cpu_percent = sample["cpu_usage_percent"]
    if cpu_percent > CPU_WARNING_THRESHOLD_PERCENT:
        LOGGER.warning(
            "High CPU usage on %s: %.1f%% (threshold: %.1f%%)",
            sample["device_id"],
            cpu_percent,
            CPU_WARNING_THRESHOLD_PERCENT,
        )


def run() -> int:
    try:
        collector = MetricsCollector()
        spool_path = os.environ.get(SPOOL_PATH_ENV, DEFAULT_SPOOL_PATH)
        spool = MetricsSpool(spool_path)
        # Validate the path at startup rather than repeatedly logging a bad path.
        psutil.disk_usage(DEFAULT_DISK_PATH)
    except (OSError, ValueError, sqlite3.Error) as exc:
        LOGGER.error("Could not initialize metric collection: %s", exc)
        return 2

    stop_event = Event()
    publisher_worker = None
    signal.signal(signal.SIGINT, partial(_request_stop, stop_event))
    signal.signal(signal.SIGTERM, partial(_request_stop, stop_event))
    if os.environ.get(GREENGRASS_IPC_SOCKET_ENV):
        try:
            publisher = GreengrassIpcPublisher()
        except RuntimeError as exc:
            LOGGER.error("Could not initialize Greengrass publisher: %s", exc)
            return 2
        publisher_worker = SpoolPublisherWorker(spool, publisher, stop_event)
        publisher_worker.start()
        LOGGER.info("Greengrass IPC publishing enabled")
    else:
        LOGGER.info("Greengrass IPC unavailable; running in local spool-only mode")
    LOGGER.info(
        "Collecting CPU, RAM, disk, and GPU metrics every %.2f seconds",
        DEFAULT_INTERVAL_SECONDS,
    )

    # Schedule against a monotonic clock to prevent collection duration from
    # accumulating as drift.
    deadline = time.monotonic()
    try:
        while not stop_event.is_set():
            try:
                sample = collector.collect()
                _log_threshold_warnings(sample)
                spool.store(sample)
                print(json.dumps(sample, separators=(",", ":")), flush=True)
            except (OSError, ValueError, sqlite3.Error) as exc:
                LOGGER.exception("Metric collection or spool write failed: %s", exc)
                return 1

            deadline += DEFAULT_INTERVAL_SECONDS
            delay = max(0.0, deadline - time.monotonic())
            if stop_event.wait(delay):
                break
            if deadline < time.monotonic() - DEFAULT_INTERVAL_SECONDS:
                deadline = time.monotonic()
    finally:
        stop_event.set()
        if publisher_worker is not None:
            publisher_worker.join(timeout=PUBLISH_TIMEOUT_SECONDS + 2)
            publisher_worker.publisher.close()
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
