"""Mock or DDS-backed telemetry for WebSocket clients."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Callable
from typing import Any

from app.joint_map import JOINT_MAP


async def mock_telemetry_stream(
    hz: float = 10.0,
    *,
    command_rad_getter: Callable[[], dict[str, float]] | None = None,
) -> Any:
    """Yield JSON lines with joint q (rad) for 29 motors + timestamp.

    When ``command_rad_getter`` is set, returned targets (rad, keys \"0\"..\"28\")
    override the default sine mock for those motors so the UI and sim preview stay
    aligned with POST /api/joints/targets until release.
    """
    period = 1.0 / max(hz, 0.1)
    t0 = time.time()
    while True:
        t = time.time() - t0
        qs = [0.05 * math.sin(t * 0.7 + i * 0.1) for i in range(29)]
        if command_rad_getter is not None:
            overlay = command_rad_getter()
            for k_str, q in overlay.items():
                try:
                    idx = int(k_str)
                except (TypeError, ValueError):
                    continue
                if not (0 <= idx < 29):
                    continue
                try:
                    qf = float(q)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(qf):
                    qs[idx] = qf
        msg = {
            "type": "lowstate",
            "timestamp_s": t,
            "mock": True,
            "joints": {str(i): qs[i] for i in range(29)},
            "joint_names": {str(i): JOINT_MAP[i] for i in range(29)},
        }
        yield json.dumps(msg) + "\n"
        await asyncio.sleep(period)
