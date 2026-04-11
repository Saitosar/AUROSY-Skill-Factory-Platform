"""
Позиционные лимиты суставов G1 (29 DOF тела, без Dexterous Hand в LowCmd).

Источник min/max: unitree_mujoco/unitree_robots/g1/g1_29dof.xml (атрибут range у joint).
Индексы 0–28 совпадают с unitree_hg LowCmd/LowState motor_cmd и JointController.JOINT_MAP.

max_vel не задан в XML — подобраны по группам (ноги / талия / руки / запястья).

Индексы 29–34 в LowCmd зарезервированы под кисти/прочее; для них DEFAULT_LIMIT не из g1_29dof.
"""

from typing import Any, Dict

# Ключи записи: min, max (рад), max_vel (рад/с), name (как в JointController.JOINT_MAP)
JOINT_LIMITS: Dict[int, Dict[str, Any]] = {
    # Ноги
    0: {"min": -2.5307, "max": 2.8798, "max_vel": 3.0, "name": "left_hip_pitch"},
    1: {"min": -0.5236, "max": 2.9671, "max_vel": 3.0, "name": "left_hip_roll"},
    2: {"min": -2.7576, "max": 2.7576, "max_vel": 3.0, "name": "left_hip_yaw"},
    3: {"min": -0.087267, "max": 2.8798, "max_vel": 4.0, "name": "left_knee"},
    4: {"min": -0.87267, "max": 0.5236, "max_vel": 3.0, "name": "left_ankle_pitch"},
    5: {"min": -0.2618, "max": 0.2618, "max_vel": 3.0, "name": "left_ankle_roll"},
    6: {"min": -2.5307, "max": 2.8798, "max_vel": 3.0, "name": "right_hip_pitch"},
    7: {"min": -2.9671, "max": 0.5236, "max_vel": 3.0, "name": "right_hip_roll"},
    8: {"min": -2.7576, "max": 2.7576, "max_vel": 3.0, "name": "right_hip_yaw"},
    9: {"min": -0.087267, "max": 2.8798, "max_vel": 4.0, "name": "right_knee"},
    10: {"min": -0.87267, "max": 0.5236, "max_vel": 3.0, "name": "right_ankle_pitch"},
    11: {"min": -0.2618, "max": 0.2618, "max_vel": 3.0, "name": "right_ankle_roll"},
    # Талия
    12: {"min": -2.618, "max": 2.618, "max_vel": 1.5, "name": "waist_yaw"},
    13: {"min": -0.52, "max": 0.52, "max_vel": 1.5, "name": "waist_roll"},
    14: {"min": -0.52, "max": 0.52, "max_vel": 1.5, "name": "waist_pitch"},
    # Левая рука
    15: {"min": -3.0892, "max": 2.6704, "max_vel": 2.0, "name": "left_shoulder_pitch"},
    16: {"min": -1.5882, "max": 2.2515, "max_vel": 2.0, "name": "left_shoulder_roll"},
    17: {"min": -2.618, "max": 2.618, "max_vel": 2.0, "name": "left_shoulder_yaw"},
    18: {"min": -1.0472, "max": 2.0944, "max_vel": 2.0, "name": "left_elbow"},
    19: {"min": -1.97222, "max": 1.97222, "max_vel": 1.5, "name": "left_wrist_roll"},
    20: {"min": -1.61443, "max": 1.61443, "max_vel": 1.0, "name": "left_wrist_pitch"},
    21: {"min": -1.61443, "max": 1.61443, "max_vel": 1.0, "name": "left_wrist_yaw"},
    # Правая рука
    22: {"min": -3.0892, "max": 2.6704, "max_vel": 2.0, "name": "right_shoulder_pitch"},
    23: {"min": -2.2515, "max": 1.5882, "max_vel": 2.0, "name": "right_shoulder_roll"},
    24: {"min": -2.618, "max": 2.618, "max_vel": 2.0, "name": "right_shoulder_yaw"},
    25: {"min": -1.0472, "max": 2.0944, "max_vel": 2.0, "name": "right_elbow"},
    26: {"min": -1.97222, "max": 1.97222, "max_vel": 1.5, "name": "right_wrist_roll"},
    27: {"min": -1.61443, "max": 1.61443, "max_vel": 1.0, "name": "right_wrist_pitch"},
    28: {"min": -1.61443, "max": 1.61443, "max_vel": 1.0, "name": "right_wrist_yaw"},
}

# Слоты 29–34 в HG LowCmd (кисти / резерв); не описаны в g1_29dof.xml
DEFAULT_LIMIT: Dict[str, Any] = {
    "min": -3.14159,
    "max": 3.14159,
    "max_vel": 1.0,
    "name": "reserved_or_hand",
}


def get_limit(joint_id: int) -> Dict[str, Any]:
    return JOINT_LIMITS.get(joint_id, DEFAULT_LIMIT)


def clamp_q(joint_id: int, q: float) -> float:
    """Ограничить целевой угол сустава диапазоном из JOINT_LIMITS / DEFAULT_LIMIT."""
    limits = get_limit(joint_id)
    lo = limits["min"]
    hi = limits["max"]
    return max(lo, min(hi, q))
