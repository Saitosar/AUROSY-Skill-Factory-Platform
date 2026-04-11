"""In-memory joint command targets for mock telemetry + HTTP API (degrees → rad)."""

from __future__ import annotations

import math
import threading
from typing import Any

_lock = threading.Lock()
_latest_rad: dict[str, float] = {}


def update_targets_deg(joints_deg: dict[str, float]) -> int:
    """Merge degrees by motor index string; returns count of accepted entries."""
    n = 0
    with _lock:
        for k, deg in joints_deg.items():
            try:
                idx = str(int(k))
            except (TypeError, ValueError):
                idx = str(k)
            _latest_rad[idx] = math.radians(float(deg))
            n += 1
    return n


def clear_targets() -> None:
    with _lock:
        _latest_rad.clear()


def snapshot_targets_rad() -> dict[str, float]:
    with _lock:
        return dict(_latest_rad)


def meta_joint_command_fields(enabled: bool) -> dict[str, Any]:
    return {"joint_command_enabled": enabled}
