# Edge Hardware Monitor

This prototype collects CPU, RAM, disk, and NVIDIA GPU metrics on Linux,
stores samples in a bounded local SQLite spool, and publishes them through
Greengrass IPC when running as a Greengrass component.

## Requirements

- Linux, such as Ubuntu 22.04
- Python 3.8+
- AWS IoT Device SDK for Python v2 1.31+ (installed from requirements)

## Install and run

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python edge_monitor.py
```

The process writes one JSON object per sample to stdout. Logs go to stderr, so
the JSON stream can be redirected to a file or collected by a service manager.
Each sample includes a UTC timestamp, hostname-based device ID, and CPU, RAM,
disk usage percentages, and NVIDIA GPU utilization as `gpu_usage_percent`.
GPU metrics are read from the first GPU reported by `nvidia-smi`; if the
NVIDIA tool or its reading is unavailable, GPU utilization is `null` and
CPU/RAM/disk collection continues. Disk usage is measured for `/`.
Samples also have a unique `sample_id`, which downstream consumers can use to
deduplicate possible QoS 1 redeliveries.

Default values are defined in `constants.py`: the sampling interval is 30
seconds (`DEFAULT_INTERVAL_SECONDS`) and the disk path is `/`
(`DEFAULT_DISK_PATH`); the NVIDIA metrics executable is `nvidia-smi`
(`NVIDIA_SMI_EXECUTABLE`). The local spool is
`~/.local/state/edge-monitor/metrics.sqlite3`
(`DEFAULT_SPOOL_PATH`). It retains up to 10,000 samples
(`MAX_SPOOLED_SAMPLES`) and expires records older than seven days
(`MAX_SAMPLE_AGE_SECONDS`); when full, oldest samples are dropped. The
collector uses these fixed defaults and takes no command-line arguments.
The SQLite schema, queries, and durability pragma are also named constants in
that file; `metrics_spool.py` executes them.

CPU sampling is primed once at startup; subsequent readings are non-blocking
and reflect usage since the preceding sample. GPU queries have a two-second
timeout. GPU collection is isolated in `gpu_metrics.py`. Samples are committed
to SQLite before being printed. When Greengrass IPC is available, a background
worker publishes the oldest stored sample to
`devices/{device_id}/metrics` with MQTT QoS 1 and removes it only after the IPC
request completes. Failed publishes remain queued and retry with exponential
backoff. QoS 1 may result in duplicate delivery if the broker accepts a sample
but the process stops before removing it from SQLite; use `sample_id` for
downstream deduplication.

Outside Greengrass, the collector detects the absence of
`AWS_GG_NUCLEUS_DOMAIN_SOCKET_FILEPATH_FOR_COMPONENT` and runs in local
spool-only mode. The SDK is installed from `requirements.txt`. For a
Greengrass component, add this permission to its recipe (replace the principal
with the deployed component name):

```yaml
accessControl:
  aws.greengrass.ipc.mqttproxy:
    com.example.EdgeHardwareMonitor:mqttproxy:1:
      policyDescription: Publish edge metrics to AWS IoT Core
      operations:
        - aws.greengrass#PublishToIoTCore
      resources:
        - devices/*/metrics
```

The Greengrass component authorization and the core device's AWS IoT policy
must both allow the publish. The runtime uses the OS hostname as `device_id`
and embeds it in the topic; ensure the IoT policy allows that topic. Narrow the
topic authorization per device where possible. The collector schedules sample
starts against a monotonic clock. Stop with Ctrl+C or SIGTERM.

## Tests

```sh
python -m unittest discover -s tests -v
```

The prototype still needs end-to-end validation on a Greengrass-enabled Linux
device with the intended GPU and AWS IoT policy.
