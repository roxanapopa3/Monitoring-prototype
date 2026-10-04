# Edge Hardware Monitor — Design

## Architecture

The monitor samples CPU, RAM, root-disk, and NVIDIA GPU utilization every 30 seconds. It records each sample—with a timestamp, hostname-based device ID, and unique sample ID—in a bounded local SQLite spool before writing it to stdout. When running as a Greengrass component, a background publisher sends queued samples through Greengrass IPC to AWS IoT Core using MQTT QoS 1. Without Greengrass IPC, it collects and stores locally.

Greengrass IPC reuses the device’s existing Greengrass connection and credentials instead of adding a separate MQTT connection or embedding cloud credentials in the application. SQLite provides local buffering while the monitor cannot hand samples to IPC. The spool is limited to 10,000 samples and seven days; the count limit can evict data sooner. GPU readings come from `nvidia-smi` for the first NVIDIA GPU and are `null` when unavailable.

## Trade-offs and delivery

A 30-second interval keeps collection lightweight, but can miss short-lived peaks. CPU readings represent the interval since the previous read; GPU utilization reflects the GPU tool’s recent measurement window. QoS 1 permits duplicate delivery, so consumers should deduplicate by `sample_id`.

The monitor removes a sample from SQLite after Greengrass IPC accepts the publish request. This confirms local handoff—not receipt by an AWS IoT Core consumer. Greengrass manages delivery after handoff under its own queue policy. The cloud consumer, storage, alerting, and stale-device detection are outside this prototype and must be selected for a deployed monitoring service.

## Scaling

At 1,000 devices and one sample every 30 seconds, the fleet produces about 33 samples per second, or 2.88 million samples per day. A cloud ingestion path should validate the schema, deduplicate samples, retain history only as needed, and track the latest observation per device. It should distinguish old replayed samples from fresh telemetry so delayed data does not hide a device that has stopped reporting. Staggering deployments and reconnects can reduce traffic bursts. Capacity, retention, and cost depend on the selected AWS destination and must be measured.

## Security

The component publishes through Greengrass IPC; it does not store AWS access keys. Its IPC authorization and the core device’s IoT policy should permit publishing only to that device’s intended topic. The prototype uses the OS hostname in `devices/{device_id}/metrics`; deployments should use a stable, commissioned device identity and keep topic authorization aligned with it. Protect the local spool with restrictive file permissions and appropriate host access controls. Avoid sending sensitive workload data in telemetry, and define retention and access controls for the cloud destination.