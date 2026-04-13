"""MediaPipe landmarks to G1 joint-angle retargeting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .joint_map import G1_JOINT_ORDER, JointMap, JointMapping, load_joint_map

_EPS = 1e-8


@dataclass(frozen=True)
class RetargetResult:
    joint_angles_rad: np.ndarray
    warnings: tuple[str, ...]


def _safe_unit(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    if norm <= _EPS:
        return np.zeros(3, dtype=np.float32)
    return (v / norm).astype(np.float32)


def _signed_angle(v1: np.ndarray, v2: np.ndarray, axis: np.ndarray) -> float:
    n1 = _safe_unit(v1)
    n2 = _safe_unit(v2)
    n_axis = _safe_unit(axis)
    if not np.any(n1) or not np.any(n2) or not np.any(n_axis):
        return 0.0
    unsigned = float(np.arccos(np.clip(float(np.dot(n1, n2)), -1.0, 1.0)))
    direction = float(np.dot(np.cross(n1, n2), n_axis))
    return unsigned if direction >= 0 else -unsigned


def angle_3points(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    v1 = p1 - p2
    v2 = p3 - p2
    if float(np.linalg.norm(v1)) <= _EPS or float(np.linalg.norm(v2)) <= _EPS:
        return 0.0
    return float(np.arccos(np.clip(float(np.dot(_safe_unit(v1), _safe_unit(v2))), -1.0, 1.0)))


class Retargeter:
    def __init__(self, joint_map: JointMap | None = None, *, clip_to_limits: bool = True):
        self.joint_map = joint_map or load_joint_map()
        self.joint_order = tuple(G1_JOINT_ORDER)
        self.clip_to_limits = clip_to_limits

    def compute(self, landmarks: np.ndarray) -> RetargetResult:
        frame = np.asarray(landmarks, dtype=np.float32)
        if frame.shape != (33, 3):
            raise ValueError("landmarks must have shape (33, 3)")
        if not np.all(np.isfinite(frame)):
            raise ValueError("landmarks must contain finite values only")

        angles = np.zeros(len(self.joint_order), dtype=np.float32)
        warnings: list[str] = []
        for idx, joint_name in enumerate(self.joint_order):
            mapping = self.joint_map.get(joint_name)
            value = self._compute_joint_angle(frame, mapping)
            if not np.isfinite(value):
                warnings.append(f"{joint_name}: non-finite value, fallback to 0")
                value = 0.0
            value = (value * mapping.scale) + mapping.offset
            if self.clip_to_limits:
                value = float(np.clip(value, mapping.limits[0], mapping.limits[1]))
            angles[idx] = value
        return RetargetResult(joint_angles_rad=angles, warnings=tuple(warnings))

    def compute_batch(self, frames: Iterable[np.ndarray]) -> tuple[np.ndarray, list[str]]:
        seq = [np.asarray(f, dtype=np.float32) for f in frames]
        if not seq:
            raise ValueError("at least one frame is required")
        out = np.zeros((len(seq), len(self.joint_order)), dtype=np.float32)
        all_warnings: list[str] = []
        for i, frame in enumerate(seq):
            result = self.compute(frame)
            out[i] = result.joint_angles_rad
            all_warnings.extend([f"frame {i}: {w}" for w in result.warnings])
        return out, all_warnings

    def _compute_joint_angle(self, landmarks: np.ndarray, mapping: JointMapping) -> float:
        idx = mapping.source_landmarks
        comp = mapping.computation
        pts = [landmarks[i] for i in idx]
        axis = np.array(mapping.reference_axis or [0.0, 0.0, 1.0], dtype=np.float32)

        if comp == "angle_3points" and len(pts) >= 3:
            return angle_3points(pts[0], pts[1], pts[2])
        if comp == "plane_angle" and len(pts) >= 3:
            return _signed_angle(pts[0] - pts[1], pts[2] - pts[1], axis)
        if comp == "angle_between_vectors" and len(pts) >= 2:
            return _signed_angle(pts[1] - pts[0], axis, axis)
        if comp == "shoulder_tilt" and len(pts) >= 2:
            v = pts[1] - pts[0]
            return float(np.arctan2(v[1], np.sqrt((v[0] * v[0]) + (v[2] * v[2]) + _EPS)))
        if comp == "torso_twist" and len(pts) >= 4:
            shoulder_vec = pts[1] - pts[0]
            hip_vec = pts[3] - pts[2]
            return _signed_angle(hip_vec, shoulder_vec, axis)
        if comp == "arm_twist" and len(pts) >= 3:
            upper = pts[1] - pts[0]
            lower = pts[2] - pts[1]
            return _signed_angle(upper, lower, axis)
        return 0.0
