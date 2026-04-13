"""Analytic IK helpers for landmark-based retargeting."""

from __future__ import annotations

import numpy as np

EPS = 1e-8


def safe_unit(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    if norm <= EPS:
        return np.zeros(3, dtype=np.float32)
    return (v / norm).astype(np.float32)


def signed_angle(v1: np.ndarray, v2: np.ndarray, axis: np.ndarray) -> float:
    n1 = safe_unit(v1)
    n2 = safe_unit(v2)
    n_axis = safe_unit(axis)
    if not np.any(n1) or not np.any(n2) or not np.any(n_axis):
        return 0.0
    unsigned = float(np.arccos(np.clip(float(np.dot(n1, n2)), -1.0, 1.0)))
    direction = float(np.dot(np.cross(n1, n2), n_axis))
    return unsigned if direction >= 0 else -unsigned


def angle_3points(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    v1 = p1 - p2
    v2 = p3 - p2
    if float(np.linalg.norm(v1)) <= EPS or float(np.linalg.norm(v2)) <= EPS:
        return 0.0
    return float(np.arccos(np.clip(float(np.dot(safe_unit(v1), safe_unit(v2))), -1.0, 1.0)))
