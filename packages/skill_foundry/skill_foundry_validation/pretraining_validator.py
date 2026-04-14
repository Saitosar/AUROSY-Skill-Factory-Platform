"""Pre-training validation checks for motion skills - safety and quality gates."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from skill_foundry_validation.report import MotionValidationReport, ValidationIssue
from skill_foundry_validation.limits_config import bundle_for_motor_index
from skill_foundry_validation.kinematic_validator import validate_kinematics


@dataclass
class PreTrainingConfig:
    """Configuration for pre-training validation."""

    max_joint_velocity_ratio: float = 0.9
    max_joint_acceleration_ratio: float = 0.8
    max_jerk_ratio: float = 0.7
    min_duration_sec: float = 0.5
    max_duration_sec: float = 120.0
    min_frame_count: int = 10
    max_consecutive_similar_frames: int = 30
    similarity_threshold: float = 0.001
    balance_check_enabled: bool = True
    com_lateral_limit: float = 0.15
    com_forward_limit: float = 0.20


@dataclass
class PreTrainingResult:
    """Result of pre-training validation."""

    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [
                {
                    "severity": i.severity,
                    "code": i.code,
                    "message": i.message,
                    "frame_index": i.frame_index,
                    "motor_index": i.motor_index,
                    "detail": i.detail,
                }
                for i in self.issues
            ],
            "warnings": [
                {
                    "severity": i.severity,
                    "code": i.code,
                    "message": i.message,
                    "frame_index": i.frame_index,
                    "motor_index": i.motor_index,
                    "detail": i.detail,
                }
                for i in self.warnings
            ],
            "notes": self.notes,
            "metrics": self.metrics,
        }


def _extract_joint_arrays(reference: dict[str, Any]) -> tuple[np.ndarray, np.ndarray | None, float]:
    """Extract position and velocity arrays from reference trajectory."""
    joint_order = [str(x) for x in reference.get("joint_order", [])]
    omap = {str(k): i for i, k in enumerate(joint_order)}

    jp = reference.get("joint_positions", [])
    jv = reference.get("joint_velocities", [])
    freq = float(reference.get("frequency_hz", 50.0))

    n_frames = len(jp)
    n_joints = len(joint_order)

    positions = np.zeros((n_frames, 29), dtype=np.float64)
    for fi, row in enumerate(jp):
        if isinstance(row, list):
            arr = np.asarray(row, dtype=np.float64).ravel()
            for mi in range(29):
                if str(mi) in omap and omap[str(mi)] < arr.size:
                    positions[fi, mi] = arr[omap[str(mi)]]

    velocities = None
    if isinstance(jv, list) and len(jv) == n_frames:
        velocities = np.zeros((n_frames, 29), dtype=np.float64)
        for fi, row in enumerate(jv):
            if isinstance(row, list):
                arr = np.asarray(row, dtype=np.float64).ravel()
                for mi in range(29):
                    if str(mi) in omap and omap[str(mi)] < arr.size:
                        velocities[fi, mi] = arr[omap[str(mi)]]

    return positions, velocities, freq


def _check_motion_stagnation(
    positions: np.ndarray,
    config: PreTrainingConfig,
) -> list[ValidationIssue]:
    """Check for frames where motion is stagnant (too similar to previous)."""
    issues = []
    n_frames = positions.shape[0]

    if n_frames < 2:
        return issues

    consecutive_similar = 0
    stagnant_start = None

    for fi in range(1, n_frames):
        diff = np.max(np.abs(positions[fi] - positions[fi - 1]))
        if diff < config.similarity_threshold:
            if consecutive_similar == 0:
                stagnant_start = fi - 1
            consecutive_similar += 1
        else:
            if consecutive_similar >= config.max_consecutive_similar_frames:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="MOTION_STAGNATION",
                        message=f"Motion appears stagnant for {consecutive_similar} frames starting at frame {stagnant_start}",
                        frame_index=stagnant_start,
                        detail={
                            "consecutive_frames": consecutive_similar,
                            "start_frame": stagnant_start,
                        },
                    )
                )
            consecutive_similar = 0
            stagnant_start = None

    if consecutive_similar >= config.max_consecutive_similar_frames:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="MOTION_STAGNATION",
                message=f"Motion appears stagnant for {consecutive_similar} frames at end starting at frame {stagnant_start}",
                frame_index=stagnant_start,
                detail={
                    "consecutive_frames": consecutive_similar,
                    "start_frame": stagnant_start,
                },
            )
        )

    return issues


def _check_safety_margins(
    positions: np.ndarray,
    velocities: np.ndarray | None,
    freq: float,
    config: PreTrainingConfig,
) -> tuple[list[ValidationIssue], dict[str, Any]]:
    """Check that motion stays within safety margins (not just limits)."""
    issues = []
    metrics = {
        "max_position_ratio": 0.0,
        "max_velocity_ratio": 0.0,
        "joints_near_limits": [],
    }

    n_frames = positions.shape[0]
    dt = 1.0 / freq

    for mi in range(29):
        bundle = bundle_for_motor_index(mi)
        q_range = bundle.q_hi - bundle.q_lo

        for fi in range(n_frames):
            q = positions[fi, mi]
            if q_range > 0:
                pos_margin_lo = (q - bundle.q_lo) / q_range
                pos_margin_hi = (bundle.q_hi - q) / q_range
                min_margin = min(pos_margin_lo, pos_margin_hi)

                if min_margin < 0.05:
                    if mi not in metrics["joints_near_limits"]:
                        metrics["joints_near_limits"].append(mi)

                    if min_margin < 0.02:
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                code="JOINT_NEAR_LIMIT",
                                message=f"Joint {mi} ({bundle.name}) is within 2% of its limit",
                                frame_index=fi,
                                motor_index=mi,
                                detail={
                                    "position": q,
                                    "margin": min_margin,
                                    "limit_lo": bundle.q_lo,
                                    "limit_hi": bundle.q_hi,
                                },
                            )
                        )

    if velocities is not None:
        for mi in range(29):
            bundle = bundle_for_motor_index(mi)
            max_vel = bundle.max_vel

            for fi in range(n_frames):
                v = abs(velocities[fi, mi])
                vel_ratio = v / max_vel if max_vel > 0 else 0

                if vel_ratio > metrics["max_velocity_ratio"]:
                    metrics["max_velocity_ratio"] = vel_ratio

                if vel_ratio > config.max_joint_velocity_ratio:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="VELOCITY_NEAR_LIMIT",
                            message=f"Joint {mi} velocity at {vel_ratio*100:.0f}% of limit",
                            frame_index=fi,
                            motor_index=mi,
                            detail={
                                "velocity": velocities[fi, mi],
                                "ratio": vel_ratio,
                                "max_vel": max_vel,
                            },
                        )
                    )

    return issues, metrics


def _check_duration_constraints(
    n_frames: int,
    freq: float,
    config: PreTrainingConfig,
) -> list[ValidationIssue]:
    """Check motion duration is within acceptable bounds."""
    issues = []
    duration = n_frames / freq

    if n_frames < config.min_frame_count:
        issues.append(
            ValidationIssue(
                severity="error",
                code="TOO_FEW_FRAMES",
                message=f"Motion has only {n_frames} frames, minimum is {config.min_frame_count}",
                detail={"frame_count": n_frames, "minimum": config.min_frame_count},
            )
        )

    if duration < config.min_duration_sec:
        issues.append(
            ValidationIssue(
                severity="error",
                code="DURATION_TOO_SHORT",
                message=f"Motion duration {duration:.2f}s is below minimum {config.min_duration_sec}s",
                detail={"duration_sec": duration, "minimum_sec": config.min_duration_sec},
            )
        )

    if duration > config.max_duration_sec:
        issues.append(
            ValidationIssue(
                severity="error",
                code="DURATION_TOO_LONG",
                message=f"Motion duration {duration:.2f}s exceeds maximum {config.max_duration_sec}s",
                detail={"duration_sec": duration, "maximum_sec": config.max_duration_sec},
            )
        )

    return issues


def validate_pretraining(
    reference: dict[str, Any],
    config: PreTrainingConfig | None = None,
) -> PreTrainingResult:
    """Run comprehensive pre-training validation on a reference trajectory.

    This function checks:
    - Basic kinematic validity (joint limits, velocities)
    - Safety margins (staying away from hard limits)
    - Motion quality (no stagnation, appropriate duration)
    - Duration constraints

    Args:
        reference: ReferenceTrajectory v1 dict
        config: Optional validation configuration

    Returns:
        PreTrainingResult with pass/fail status and detailed issues
    """
    cfg = config or PreTrainingConfig()
    issues: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    notes: list[str] = []
    metrics: dict[str, Any] = {}

    kinematics_report = validate_kinematics(reference)

    for issue in kinematics_report.issues:
        if issue.severity == "error":
            issues.append(issue)
        else:
            warnings.append(issue)

    positions, velocities, freq = _extract_joint_arrays(reference)
    n_frames = positions.shape[0]

    duration_issues = _check_duration_constraints(n_frames, freq, cfg)
    for issue in duration_issues:
        if issue.severity == "error":
            issues.append(issue)
        else:
            warnings.append(issue)

    stagnation_issues = _check_motion_stagnation(positions, cfg)
    warnings.extend(stagnation_issues)

    safety_issues, safety_metrics = _check_safety_margins(positions, velocities, freq, cfg)
    warnings.extend(safety_issues)
    metrics.update(safety_metrics)

    metrics["duration_sec"] = n_frames / freq
    metrics["frame_count"] = n_frames
    metrics["frequency_hz"] = freq
    metrics["kinematic_errors"] = len([i for i in kinematics_report.issues if i.severity == "error"])
    metrics["kinematic_warnings"] = len([i for i in kinematics_report.issues if i.severity != "error"])

    passed = len(issues) == 0

    if passed:
        notes.append("Pre-training validation passed - motion is safe for RL training")
    else:
        notes.append(f"Pre-training validation failed with {len(issues)} error(s)")

    if len(warnings) > 0:
        notes.append(f"{len(warnings)} warning(s) found - review recommended before training")

    return PreTrainingResult(
        passed=passed,
        issues=issues,
        warnings=warnings,
        notes=notes,
        metrics=metrics,
    )


def validate_pretraining_from_path(
    path: str | Path,
    config: PreTrainingConfig | None = None,
) -> PreTrainingResult:
    """Load reference trajectory from file and validate for pre-training."""
    p = Path(path)
    data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return validate_pretraining(data, config=config)
