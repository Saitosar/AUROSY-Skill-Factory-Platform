"""Joint mapping configuration for MediaPipe(33) -> G1(29) retargeting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

G1_JOINT_ORDER = [
    "left_hip_pitch",
    "left_hip_roll",
    "left_hip_yaw",
    "left_knee",
    "left_ankle_pitch",
    "left_ankle_roll",
    "right_hip_pitch",
    "right_hip_roll",
    "right_hip_yaw",
    "right_knee",
    "right_ankle_pitch",
    "right_ankle_roll",
    "waist_yaw",
    "waist_roll",
    "waist_pitch",
    "left_shoulder_pitch",
    "left_shoulder_roll",
    "left_shoulder_yaw",
    "left_elbow",
    "left_wrist_roll",
    "left_wrist_pitch",
    "left_wrist_yaw",
    "right_shoulder_pitch",
    "right_shoulder_roll",
    "right_shoulder_yaw",
    "right_elbow",
    "right_wrist_roll",
    "right_wrist_pitch",
    "right_wrist_yaw",
]


@dataclass(frozen=True)
class JointMapping:
    source_landmarks: tuple[int, ...]
    computation: str
    scale: float
    offset: float
    limits: tuple[float, float]
    reference_axis: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class JointMap:
    version: str
    source_skeleton: str
    target_robot: str
    mappings: dict[str, JointMapping]

    def get(self, joint_name: str) -> JointMapping:
        if joint_name not in self.mappings:
            raise KeyError(f"joint mapping not found: {joint_name}")
        return self.mappings[joint_name]


def _default_joint_map_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "skill_foundry_validation"
        / "models"
        / "g1_description"
        / "joint_map.json"
    )


def _parse_mapping(joint_name: str, raw: dict[str, Any]) -> JointMapping:
    if "source_landmarks" not in raw or "computation" not in raw:
        raise ValueError(f"mapping '{joint_name}' must contain source_landmarks and computation")
    source_landmarks = tuple(int(x) for x in raw["source_landmarks"])
    if not source_landmarks:
        raise ValueError(f"mapping '{joint_name}' has empty source_landmarks")

    limits_raw = raw.get("limits", [-3.14159, 3.14159])
    if not isinstance(limits_raw, list | tuple) or len(limits_raw) != 2:
        raise ValueError(f"mapping '{joint_name}' has invalid limits")
    lo, hi = float(limits_raw[0]), float(limits_raw[1])
    if lo > hi:
        raise ValueError(f"mapping '{joint_name}' has inverted limits")

    ref_axis = raw.get("reference_axis")
    ref_tuple: tuple[float, float, float] | None = None
    if ref_axis is not None:
        if not isinstance(ref_axis, list | tuple) or len(ref_axis) != 3:
            raise ValueError(f"mapping '{joint_name}' has invalid reference_axis")
        ref_tuple = (float(ref_axis[0]), float(ref_axis[1]), float(ref_axis[2]))

    return JointMapping(
        source_landmarks=source_landmarks,
        computation=str(raw["computation"]),
        scale=float(raw.get("scale", 1.0)),
        offset=float(raw.get("offset", 0.0)),
        limits=(lo, hi),
        reference_axis=ref_tuple,
    )


def load_joint_map(path: Path | None = None) -> JointMap:
    joint_map_path = path or _default_joint_map_path()
    payload = json.loads(joint_map_path.read_text(encoding="utf-8"))

    if payload.get("source_skeleton") != "mediapipe_pose_33":
        raise ValueError("joint_map source_skeleton must be mediapipe_pose_33")
    if payload.get("target_robot") != "unitree_g1_29dof":
        raise ValueError("joint_map target_robot must be unitree_g1_29dof")

    mappings_raw = payload.get("mappings")
    if not isinstance(mappings_raw, dict):
        raise ValueError("joint_map mappings must be an object")

    mappings = {name: _parse_mapping(name, cfg) for name, cfg in mappings_raw.items()}
    missing = [joint for joint in G1_JOINT_ORDER if joint not in mappings]
    if missing:
        raise ValueError(f"joint_map missing required joints: {', '.join(missing)}")

    return JointMap(
        version=str(payload.get("version", "1.0")),
        source_skeleton=str(payload["source_skeleton"]),
        target_robot=str(payload["target_robot"]),
        mappings=mappings,
    )
