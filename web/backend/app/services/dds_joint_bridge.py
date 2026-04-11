"""
Publish Unitree HG ``rt/lowcmd`` from in-memory joint targets (web UI).

MuJoCo ``unitree_sdk2py_bridge`` applies the *latest* LowCmd message each step; without a
steady stream (like Tk ``pose_studio.py`` at ~75 Hz), a single HTTP-triggered publish is
easily overwritten by other DDS traffic or fails to hold PD targets. This thread mirrors
that behaviour for the browser Motion Studio.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

NUM_HG_MOTORS = 35


def _loop(settings: Settings, stop: threading.Event) -> None:
    from app.services.sdk_path import ensure_sdk_on_path

    ensure_sdk_on_path(
        settings.resolved_sdk_root(),
        settings.resolved_skill_foundry_root(),
    )

    try:
        from core_control.joint_controller import JointController
    except ImportError as e:
        logger.warning("DDS joint bridge skipped (import): %s", e)
        return

    try:
        ctrl = JointController(
            domain_id=int(settings.dds_domain_id),
            interface=str(settings.dds_interface),
        )
    except Exception as e:
        logger.warning("DDS joint bridge skipped (init): %s", e)
        return

    hz = max(float(settings.dds_joint_publish_hz), 1.0)
    period = 1.0 / hz
    had_targets = False

    from app.joint_command import snapshot_targets_rad

    logger.info(
        "DDS joint bridge running (%.0f Hz, domain=%s iface=%s)",
        hz,
        settings.dds_domain_id,
        settings.dds_interface,
    )

    while not stop.is_set():
        t0 = time.perf_counter()
        targets = snapshot_targets_rad()
        try:
            if targets:
                had_targets = True
                for i in range(NUM_HG_MOTORS):
                    k = str(i)
                    if k in targets:
                        ctrl.set_joint(i, float(targets[k]))
                    else:
                        ctrl.set_motor_passive(i)
                ctrl.publish()
            elif had_targets:
                ctrl.set_all_motors_passive(NUM_HG_MOTORS)
                ctrl.publish()
                had_targets = False
        except Exception:
            logger.exception("DDS joint bridge publish failed")
        elapsed = time.perf_counter() - t0
        sleep_for = period - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)


class DdsJointBridge:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, settings: Settings) -> None:
        self._thread = threading.Thread(
            target=_loop,
            args=(settings, self._stop),
            name="dds-joint-bridge",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)


def maybe_start_dds_joint_bridge(settings: Settings) -> DdsJointBridge | None:
    if not settings.joint_command_enabled or not settings.dds_joint_bridge:
        return None
    b = DdsJointBridge()
    b.start(settings)
    return b
