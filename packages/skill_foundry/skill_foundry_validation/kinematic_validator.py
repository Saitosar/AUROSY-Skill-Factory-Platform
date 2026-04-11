"""Joint-space kinematic checks: q, dq, ddq, jerk vs consolidated limits."""

from __future__ import annotations

from typing import Any

import numpy as np

from skill_foundry_validation.limits_config import bundle_for_motor_index
from skill_foundry_validation.report import MotionValidationReport, ValidationIssue


def _order_map(joint_order: list[str]) -> dict[str, int]:
    return {str(k): i for i, k in enumerate(joint_order)}


def validate_kinematics(reference: dict[str, Any]) -> MotionValidationReport:
    """
    Validate ReferenceTrajectory v1 joint_positions and optional joint_velocities.

    Uses motor indices 0..28 aligned with ``core_control.config.joint_limits``.
    """
    order_raw = reference.get("joint_order")
    if not isinstance(order_raw, list) or not order_raw:
        return MotionValidationReport(
            ok=False,
            issues=[
                ValidationIssue(
                    severity="error",
                    code="invalid_joint_order",
                    message="reference_trajectory.joint_order must be a non-empty list",
                )
            ],
        )
    joint_order = [str(x) for x in order_raw]
    for mi in range(29):
        if str(mi) not in joint_order:
            return MotionValidationReport(
                ok=False,
                issues=[
                    ValidationIssue(
                        severity="error",
                        code="joint_order_missing_motor",
                        message=f"joint_order must include motor index {mi} as string key",
                    )
                ],
            )
    omap = _order_map(joint_order)

    jp = reference.get("joint_positions")
    if not isinstance(jp, list) or len(jp) == 0:
        return MotionValidationReport(
            ok=False,
            issues=[
                ValidationIssue(
                    severity="error",
                    code="invalid_joint_positions",
                    message="joint_positions must be a non-empty list of samples",
                )
            ],
        )

    freq = float(reference.get("frequency_hz", 50.0))
    if freq <= 0:
        return MotionValidationReport(
            ok=False,
            issues=[
                ValidationIssue(
                    severity="error",
                    code="invalid_frequency",
                    message="frequency_hz must be positive",
                )
            ],
        )
    dt = 1.0 / freq

    jv = reference.get("joint_velocities")
    velocities: np.ndarray | None = None
    if isinstance(jv, list) and len(jv) == len(jp):
        velocities = np.asarray(jv, dtype=np.float64)
        if velocities.ndim != 2:
            velocities = None

    issues: list[ValidationIssue] = []
    n_frames = len(jp)

    for fi, row in enumerate(jp):
        if not isinstance(row, list):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="bad_position_row",
                    message=f"joint_positions[{fi}] must be a list",
                    frame_index=fi,
                )
            )
            continue
        arr = np.asarray(row, dtype=np.float64).ravel()
        expected = len(joint_order)
        if arr.size < expected:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="short_row",
                    message=f"joint_positions[{fi}] length {arr.size} < joint_order {expected}",
                    frame_index=fi,
                )
            )
            continue
        for mi in range(29):
            q = float(arr[omap[str(mi)]])
            b = bundle_for_motor_index(mi)
            if q < b.q_lo - 1e-5 or q > b.q_hi + 1e-5:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="position_limit",
                        message=f"joint {mi} ({b.name}) position out of limit",
                        frame_index=fi,
                        motor_index=mi,
                        detail={"q": q, "lo": b.q_lo, "hi": b.q_hi},
                    )
                )

    if velocities is not None and velocities.shape[0] == n_frames:
        ncol = velocities.shape[1] if velocities.ndim == 2 else 0
        if ncol < len(joint_order):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="velocity_shape",
                    message="joint_velocities columns must match joint_order length",
                )
            )
        else:
            for fi in range(n_frames):
                for mi in range(29):
                    dqj = float(velocities[fi, omap[str(mi)]])
                    b = bundle_for_motor_index(mi)
                    if abs(dqj) > b.max_vel + 1e-5:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                code="velocity_limit",
                                message=f"joint {mi} ({b.name}) |dq| exceeds max_vel",
                                frame_index=fi,
                                motor_index=mi,
                                detail={"dq": dqj, "max_vel": b.max_vel},
                            )
                        )

            for fi in range(1, n_frames):
                for mi in range(29):
                    ddq = float(
                        (velocities[fi, omap[str(mi)]] - velocities[fi - 1, omap[str(mi)]]) / dt
                    )
                    b = bundle_for_motor_index(mi)
                    if abs(ddq) > b.max_abs_ddq:
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                code="acceleration_high",
                                message=f"joint {mi} ({b.name}) |ddq| exceeds recommended cap",
                                frame_index=fi,
                                motor_index=mi,
                                detail={"ddq": ddq, "cap": b.max_abs_ddq},
                            )
                        )

            if n_frames >= 3:
                for fi in range(2, n_frames):
                    for mi in range(29):
                        ci = omap[str(mi)]
                        ddq0 = (velocities[fi - 1, ci] - velocities[fi - 2, ci]) / dt
                        ddq1 = (velocities[fi, ci] - velocities[fi - 1, ci]) / dt
                        jerk = float((ddq1 - ddq0) / dt)
                        b = bundle_for_motor_index(mi)
                        if abs(jerk) > b.max_abs_jerk:
                            issues.append(
                                ValidationIssue(
                                    severity="warning",
                                    code="jerk_high",
                                    message=f"joint {mi} ({b.name}) |jerk| exceeds recommended cap",
                                    frame_index=fi,
                                    motor_index=mi,
                                    detail={"jerk": jerk, "cap": b.max_abs_jerk},
                                )
                            )
    elif n_frames >= 2:
        for fi in range(1, n_frames):
            row = jp[fi]
            prev = jp[fi - 1]
            if not isinstance(row, list) or not isinstance(prev, list):
                continue
            arr = np.asarray(row, dtype=np.float64).ravel()
            arrp = np.asarray(prev, dtype=np.float64).ravel()
            if arr.size < len(joint_order) or arrp.size < len(joint_order):
                continue
            for mi in range(29):
                ci = omap[str(mi)]
                dq = (float(arr[ci]) - float(arrp[ci])) / dt
                b = bundle_for_motor_index(mi)
                if abs(dq) > b.max_vel + 1e-5:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="velocity_fd_high",
                            message=f"joint {mi} ({b.name}) finite-diff |dq| exceeds max_vel",
                            frame_index=fi,
                            motor_index=mi,
                            detail={"dq_fd": dq, "max_vel": b.max_vel},
                        )
                    )

    err = any(i.severity == "error" for i in issues)
    return MotionValidationReport(ok=not err, issues=issues)
