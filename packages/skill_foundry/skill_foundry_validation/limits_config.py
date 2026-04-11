"""Consolidated G1 limits: q, dq, ddq, tau (from MJCF actuatorfrcrange + joint_limits)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core_control.config.joint_limits import JOINT_LIMITS, get_limit

# N·m — from unitree_mujoco g1_29dof.xml joint actuatorfrcrange (absolute max per motor index)
TORQUE_LIMIT_NM: dict[int, float] = {
    0: 88.0,
    1: 88.0,
    2: 88.0,
    3: 139.0,
    4: 50.0,
    5: 50.0,
    6: 88.0,
    7: 88.0,
    8: 88.0,
    9: 139.0,
    10: 50.0,
    11: 50.0,
    12: 88.0,
    13: 50.0,
    14: 50.0,
    15: 25.0,
    16: 25.0,
    17: 25.0,
    18: 25.0,
    19: 25.0,
    20: 5.0,
    21: 5.0,
    22: 25.0,
    23: 25.0,
    24: 25.0,
    25: 25.0,
    26: 25.0,
    27: 5.0,
    28: 5.0,
}

# Default acceleration cap (rad/s²) when not using Pinocchio — conservative guard
DEFAULT_MAX_ABS_DDQ: dict[int, float] = {i: 80.0 for i in range(29)}

# Default jerk cap (rad/s³)
DEFAULT_MAX_ABS_JERK: dict[int, float] = {i: 2000.0 for i in range(29)}


@dataclass(frozen=True)
class JointLimitBundle:
    q_lo: float
    q_hi: float
    max_vel: float
    max_tau: float
    max_abs_ddq: float
    max_abs_jerk: float
    name: str


def bundle_for_motor_index(idx: int) -> JointLimitBundle:
    lim = get_limit(idx)
    return JointLimitBundle(
        q_lo=float(lim["min"]),
        q_hi=float(lim["max"]),
        max_vel=float(lim["max_vel"]),
        max_tau=float(TORQUE_LIMIT_NM.get(idx, 25.0)),
        max_abs_ddq=float(DEFAULT_MAX_ABS_DDQ.get(idx, 80.0)),
        max_abs_jerk=float(DEFAULT_MAX_ABS_JERK.get(idx, 2000.0)),
        name=str(lim.get("name", f"joint_{idx}")),
    )


def all_bundles() -> list[JointLimitBundle]:
    return [bundle_for_motor_index(i) for i in range(29)]


def limits_dict_for_yaml() -> dict[str, Any]:
    rows = []
    for i in range(29):
        b = bundle_for_motor_index(i)
        rows.append(
            {
                "index": i,
                "name": b.name,
                "q_min_rad": b.q_lo,
                "q_max_rad": b.q_hi,
                "max_vel_rad_s": b.max_vel,
                "max_tau_nm": b.max_tau,
                "max_abs_ddq_rad_s2": b.max_abs_ddq,
                "max_abs_jerk_rad_s3": b.max_abs_jerk,
            }
        )
    return {"robot": "g1_29dof", "motors": rows}
