"""Run skill_foundry_validation on a ReferenceTrajectory dict (in-process, SDK on path)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from app.services.sdk_path import ensure_sdk_on_path


def run_motion_validation(
    sdk_root: Path,
    skill_foundry_root: Path,
    reference_trajectory: dict[str, Any],
    mjcf_path: str | None,
    *,
    validate_motion: bool = True,
) -> dict[str, Any] | None:
    """
    Returns a JSON-serializable report dict, or None if skipped/failed to import.

    On import errors (e.g. optional Pinocchio missing), kinematic + MuJoCo stages still run.
    """
    if not validate_motion:
        return None

    ensure_sdk_on_path(sdk_root, skill_foundry_root)
    if "skill_foundry_validation" not in sys.modules:
        import importlib

        importlib.invalidate_caches()

    try:
        from skill_foundry_validation.motion_validator import MotionValidatorConfig, validate_reference_motion
    except ImportError as e:
        return {"ok": False, "import_error": str(e), "issues": []}

    cfg = MotionValidatorConfig(
        mjcf_path=mjcf_path,
        check_kinematics=True,
        check_collision=bool(mjcf_path),
        check_torque_rnea=True,
        collision_frame_stride=1,
        torque_frame_stride=5,
    )
    report = validate_reference_motion(reference_trajectory, config=cfg)
    return report.to_dict()
