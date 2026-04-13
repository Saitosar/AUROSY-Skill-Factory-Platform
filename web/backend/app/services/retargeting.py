"""In-process bridge to skill_foundry_retarget package."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.services.sdk_path import ensure_sdk_on_path


@dataclass(frozen=True)
class RetargetServiceResult:
    joint_order: list[str]
    joint_angles_rad: np.ndarray
    warnings: list[str]
    mapping_version: str
    source_skeleton: str
    target_robot: str
    elapsed_ms: float


def run_retargeting(
    *,
    sdk_root: Path,
    skill_foundry_root: Path,
    frames: np.ndarray,
    source_skeleton: str,
    target_robot: str,
    clip_to_limits: bool,
) -> RetargetServiceResult:
    ensure_sdk_on_path(sdk_root, skill_foundry_root)

    from skill_foundry_retarget import Retargeter, load_joint_map

    joint_map = load_joint_map()
    if source_skeleton != joint_map.source_skeleton:
        raise ValueError(f"unsupported source_skeleton: {source_skeleton}")
    if target_robot != joint_map.target_robot:
        raise ValueError(f"unsupported target_robot: {target_robot}")

    retargeter = Retargeter(joint_map=joint_map, clip_to_limits=clip_to_limits)
    t0 = time.perf_counter()
    joint_angles_rad, warnings = retargeter.compute_batch(frames)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return RetargetServiceResult(
        joint_order=list(retargeter.joint_order),
        joint_angles_rad=joint_angles_rad,
        warnings=warnings,
        mapping_version=joint_map.version,
        source_skeleton=joint_map.source_skeleton,
        target_robot=joint_map.target_robot,
        elapsed_ms=elapsed_ms,
    )


def parse_landmarks_payload(landmarks: Any) -> tuple[np.ndarray, bool]:
    arr = np.asarray(landmarks, dtype=np.float32)
    if arr.ndim == 2:
        if arr.shape != (33, 3):
            raise ValueError("landmarks frame must have shape [33, 3]")
        return arr[np.newaxis, ...], False
    if arr.ndim == 3:
        if arr.shape[1:] != (33, 3):
            raise ValueError("landmarks sequence must have shape [N, 33, 3]")
        if arr.shape[0] == 0:
            raise ValueError("landmarks sequence must contain at least one frame")
        return arr, True
    raise ValueError("landmarks must be [33,3] or [N,33,3]")
