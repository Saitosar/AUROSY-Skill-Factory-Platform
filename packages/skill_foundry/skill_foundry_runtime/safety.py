"""Joint/torque limits: clip torques, count violations, request stop."""

from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np


def actuator_joint_limits(model: mujoco.MjModel) -> tuple[np.ndarray, np.ndarray]:
    """Per-actuator soft limits from bound joints (inf if unlimited)."""
    nu = int(model.nu)
    q_low = np.full(nu, -np.inf, dtype=np.float64)
    q_high = np.full(nu, np.inf, dtype=np.float64)
    for i in range(nu):
        jid = int(model.actuator_trnid[i, 0])
        if jid < 0:
            continue
        if bool(model.jnt_limited[jid]):
            q_low[i] = float(model.jnt_range[jid, 0])
            q_high[i] = float(model.jnt_range[jid, 1])
    return q_low, q_high


@dataclass
class SafetyConfig:
    """Prototype safety: clip torque magnitude; stop after repeated limit breaches."""

    max_abs_tau: float = 120.0
    max_consecutive_torque_clips: int = 50
    max_consecutive_q_violations: int = 5
    max_abs_dq: float | None = None
    """If set, treat |motor_dq| or |dq_des| above this (rad/s) as a velocity violation."""
    max_consecutive_dq_violations: int = 5


class SafetyMonitor:
    def __init__(
        self,
        q_low: np.ndarray,
        q_high: np.ndarray,
        cfg: SafetyConfig | None = None,
    ) -> None:
        self._q_low = np.asarray(q_low, dtype=np.float64)
        self._q_high = np.asarray(q_high, dtype=np.float64)
        self._cfg = cfg or SafetyConfig()
        self._clip_streak = 0
        self._q_streak = 0
        self._dq_streak = 0

    def reset(self) -> None:
        self._clip_streak = 0
        self._q_streak = 0
        self._dq_streak = 0

    def process(
        self,
        tau: np.ndarray,
        motor_q: np.ndarray,
        motor_dq: np.ndarray,
        q_des: np.ndarray,
        dq_des: np.ndarray | None = None,
    ) -> tuple[np.ndarray, bool, str]:
        """
        Clip ``tau`` to ``±max_abs_tau``. Track measured joint limit violations.

        Returns ``(tau_out, stop, reason)``. ``stop`` is True when streaks exceed
        configured thresholds.
        """
        tau = np.asarray(tau, dtype=np.float64).ravel().copy()
        m = float(self._cfg.max_abs_tau)
        before = tau.copy()
        np.clip(tau, -m, m, out=tau)
        if not np.allclose(before, tau):
            self._clip_streak += 1
        else:
            self._clip_streak = 0

        mq = np.asarray(motor_q, dtype=np.float64).ravel()
        q_bad = np.any(mq < self._q_low - 1e-6) or np.any(mq > self._q_high + 1e-6)
        qd = np.asarray(q_des, dtype=np.float64).ravel()
        des_bad = np.any(qd < self._q_low - 1e-3) or np.any(qd > self._q_high + 1e-3)
        if q_bad or des_bad:
            self._q_streak += 1
        else:
            self._q_streak = 0

        lim_dq = self._cfg.max_abs_dq
        if lim_dq is not None and float(lim_dq) > 0:
            mdq = np.asarray(motor_dq, dtype=np.float64).ravel()
            dq_bad = bool(np.any(np.abs(mdq) > float(lim_dq) + 1e-9))
            if dq_des is not None:
                dd = np.asarray(dq_des, dtype=np.float64).ravel()
                dq_bad = dq_bad or bool(np.any(np.abs(dd) > float(lim_dq) + 1e-9))
            if dq_bad:
                self._dq_streak += 1
            else:
                self._dq_streak = 0
        else:
            self._dq_streak = 0

        reason = ""
        stop = False
        if self._clip_streak >= self._cfg.max_consecutive_torque_clips:
            stop = True
            reason = "torque clipped too many steps in a row"
        if self._q_streak >= self._cfg.max_consecutive_q_violations:
            stop = True
            reason = "joint or q_des outside limits repeatedly"
        if self._dq_streak >= self._cfg.max_consecutive_dq_violations:
            stop = True
            reason = "motor_dq or dq_des above max_abs_dq repeatedly"

        return tau, stop, reason
