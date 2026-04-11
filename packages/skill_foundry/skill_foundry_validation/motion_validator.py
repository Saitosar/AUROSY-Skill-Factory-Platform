"""Orchestrate kinematic, optional Pinocchio torque, and MuJoCo collision checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skill_foundry_phase0.contract_validator import validate_reference_trajectory_dict

from skill_foundry_validation.collision_mujoco import validate_self_collision_mujoco
from skill_foundry_validation.kinematic_validator import validate_kinematics
from skill_foundry_validation.pinocchio_dynamics import validate_torque_rnea
from skill_foundry_validation.report import MotionValidationReport, ValidationIssue


@dataclass
class MotionValidatorConfig:
    """Configure which stages run (all on by default)."""

    check_kinematics: bool = True
    check_collision: bool = True
    check_torque_rnea: bool = True
    collision_frame_stride: int = 1
    torque_frame_stride: int = 5
    mjcf_path: str | None = None
    urdf_path: str | None = None


def _merge_reports(*reports: MotionValidationReport) -> MotionValidationReport:
    issues: list[ValidationIssue] = []
    notes: list[str] = []
    pin_used = False
    col_eng = "not_run"
    for r in reports:
        issues.extend(r.issues)
        notes.extend(r.notes)
        if r.pinocchio_used:
            pin_used = True
        if r.collision_engine == "mujoco":
            col_eng = "mujoco"
        elif r.collision_engine not in ("not_run", "none") and col_eng == "not_run":
            col_eng = r.collision_engine
    err = any(i.severity == "error" for i in issues)
    return MotionValidationReport(
        ok=not err,
        issues=issues,
        pinocchio_used=pin_used,
        collision_engine=col_eng,
        notes=notes,
    )


def validate_reference_motion(
    reference: dict[str, Any],
    config: MotionValidatorConfig | None = None,
) -> MotionValidationReport:
    """
    Full pipeline: Phase 0 contract → kinematics → optional RNEA → optional MuJoCo self-collision.

    Parameters
    ----------
    reference
        ReferenceTrajectory v1 dict.
    config
        Optional toggles and paths. ``mjcf_path`` defaults to env / caller must pass for collision.
    """
    cfg = config or MotionValidatorConfig()

    contract_errors = validate_reference_trajectory_dict(reference)
    if contract_errors:
        return MotionValidationReport(
            ok=False,
            issues=[
                ValidationIssue(
                    severity="error",
                    code="contract",
                    message=e,
                )
                for e in contract_errors
            ],
        )

    parts: list[MotionValidationReport] = []

    if cfg.check_kinematics:
        parts.append(validate_kinematics(reference))

    if cfg.check_torque_rnea:
        parts.append(
            validate_torque_rnea(
                reference,
                urdf_path=cfg.urdf_path,
                frame_stride=cfg.torque_frame_stride,
            )
        )

    if cfg.check_collision and cfg.mjcf_path:
        parts.append(
            validate_self_collision_mujoco(
                reference,
                cfg.mjcf_path,
                frame_stride=cfg.collision_frame_stride,
            )
        )
    elif cfg.check_collision and not cfg.mjcf_path:
        parts.append(
            MotionValidationReport(
                ok=True,
                notes=["MJCF path not set; skipped self-collision check"],
            )
        )

    return _merge_reports(*parts) if parts else MotionValidationReport(ok=True)


def validate_reference_motion_from_path(
    path: str | Path,
    config: MotionValidatorConfig | None = None,
) -> MotionValidationReport:
    import json

    p = Path(path)
    data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return validate_reference_motion(data, config=config)
