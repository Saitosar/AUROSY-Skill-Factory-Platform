"""Residual PD torque (same law as :class:`G1TrackingEnv`)."""

from __future__ import annotations

from typing import Any

import numpy as np


def build_q_dq_des(
    motor_q: np.ndarray,
    motor_dq: np.ndarray,
    row_q: np.ndarray,
    row_dq: np.ndarray,
    joint_order: list[Any],
) -> tuple[np.ndarray, np.ndarray]:
    """Motor-order desired q, dq: reference joints set; others keep measured."""
    q_des = np.asarray(motor_q, dtype=np.float64).copy()
    dq_des = np.asarray(motor_dq, dtype=np.float64).copy()
    for col, jid_str in enumerate(joint_order):
        mi = int(str(jid_str))
        q_des[mi] = float(row_q[col])
        dq_des[mi] = float(row_dq[col])
    return q_des, dq_des


def residual_pd_torque(
    action: np.ndarray,
    motor_q: np.ndarray,
    motor_dq: np.ndarray,
    row_q: np.ndarray,
    row_dq: np.ndarray,
    joint_order: list[Any],
    *,
    delta_max: float,
    kp: float,
    kd: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns ``(tau, q_des, dq_des)`` after applying clipped action residual to
    reference motor targets.
    """
    a = np.clip(np.asarray(action, dtype=np.float64).ravel(), -1.0, 1.0)
    delta = a * float(delta_max)
    q_des, dq_des = build_q_dq_des(motor_q, motor_dq, row_q, row_dq, joint_order)
    q_des = q_des + delta
    q_m = np.asarray(motor_q, dtype=np.float64).ravel()
    dq_m = np.asarray(motor_dq, dtype=np.float64).ravel()
    tau = kp * (q_des - q_m) + kd * (dq_des - dq_m)
    return tau.astype(np.float64), q_des, dq_des
