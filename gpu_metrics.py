"""GPU metric collection backends."""

import logging
import subprocess
from typing import Optional

from constants import NVIDIA_SMI_EXECUTABLE

LOGGER = logging.getLogger("edge_monitor.gpu")


class NvidiaGpuCollector:
    """Collect metrics for the first NVIDIA GPU using nvidia-smi."""

    def __init__(
        self,
        executable: str = NVIDIA_SMI_EXECUTABLE,
        timeout_seconds: float = 2.0,
    ):
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def collect(self) -> Optional[float]:
        query = "utilization.gpu"
        try:
            result = subprocess.run(
                [
                    self.executable,
                    f"--query-gpu={query}",
                    "--format=csv,noheader,nounits",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            lines = result.stdout.strip().splitlines()
            if not lines:
                raise ValueError("nvidia-smi returned no GPU data")
            fields = [field.strip() for field in lines[0].split(",")]
            if len(fields) != 1:
                raise ValueError("unexpected nvidia-smi output format")

            return _parse_optional_number(fields[0])
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            LOGGER.warning("NVIDIA GPU metrics unavailable: %s", exc)
            return None


def _parse_optional_number(value: str) -> Optional[float]:
    if value.strip().lower() in {"n/a", "[n/a]", "not supported"}:
        return None
    return float(value.strip())
