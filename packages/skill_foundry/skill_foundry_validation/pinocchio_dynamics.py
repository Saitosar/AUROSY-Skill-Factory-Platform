"""Optional Pinocchio RNEA torque check (requires ``pin`` / pinocchio)."""

from __future__ import annotations

from typing import Any

import numpy as np

from skill_foundry_validation.limits_config import bundle_for_motor_index
from skill_foundry_validation.paths import default_g1_urdf_path, default_package_dir_for_urdf
from skill_foundry_validation.report import MotionValidationReport, ValidationIssue


def _order_map(reference: dict[str, Any]) -> dict[str, int]:
    joint_order = [str(x) for x in reference["joint_order"]]
    return {str(k): i for i, k in enumerate(joint_order)}


def _row_to_q29(reference: dict[str, Any], row: list[float]) -> np.ndarray:
    omap = _order_map(reference)
    arr = np.asarray(row, dtype=np.float64).ravel()
    q = np.zeros(29, dtype=np.float64)
    for mi in range(29):
        ci = omap[str(mi)]
        q[mi] = float(arr[ci])
    return q


def _motor_vel_row(reference: dict[str, Any], velocities_row: np.ndarray) -> np.ndarray:
    omap = _order_map(reference)
    out = np.zeros(29, dtype=np.float64)
    for mi in range(29):
        out[mi] = float(velocities_row[omap[str(mi)]])
    return out


def validate_torque_rnea(
    reference: dict[str, Any],
    *,
    urdf_path: str | None = None,
    frame_stride: int = 5,
) -> MotionValidationReport:
    """
    If Pinocchio is installed, run RNEA with accelerations from joint_velocities (or finite diff).

    Otherwise returns ok=True with a note (skipped).
    """
    try:
        import pinocchio as pin  # type: ignore[import-untyped]
    except ImportError:
        return MotionValidationReport(
            ok=True,
            pinocchio_used=False,
            notes=["Pinocchio not installed; skipped RNEA torque check. Install extra: pip install pin"],
        )

    path = urdf_path or str(default_g1_urdf_path())
    pkg = str(default_package_dir_for_urdf())
    try:
        model = pin.buildModelFromUrdf(path, package_dirs=[pkg])
    except Exception as e:  # noqa: BLE001
        return MotionValidationReport(
            ok=False,
            pinocchio_used=True,
            issues=[
                ValidationIssue(
                    severity="error",
                    code="pinocchio_load_failed",
                    message=f"failed to load URDF: {e}",
                )
            ],
        )

    if model.nq != 29 or model.nv != 29:
        return MotionValidationReport(
            ok=False,
            pinocchio_used=True,
            issues=[
                ValidationIssue(
                    severity="error",
                    code="pinocchio_dof_mismatch",
                    message=f"expected nq=nv=29, got nq={model.nq} nv={model.nv} (URDF base joint?)",
                )
            ],
        )

    data = model.createData()
    jp = reference.get("joint_positions")
    jv = reference.get("joint_velocities")
    freq = float(reference.get("frequency_hz", 50.0))
    dt = 1.0 / freq

    if not isinstance(jp, list) or len(jp) < 2:
        return MotionValidationReport(ok=True, pinocchio_used=True, notes=["not enough samples for RNEA"])

    velocities_table: np.ndarray | None = None
    if isinstance(jv, list) and len(jv) == len(jp):
        velocities_table = np.asarray(jv, dtype=np.float64)

    issues: list[ValidationIssue] = []
    n = len(jp)
    stride = max(1, int(frame_stride))

    for fi in range(1, n, stride):
        q = _row_to_q29(reference, jp[fi])
        if velocities_table is not None:
            dq = _motor_vel_row(reference, velocities_table[fi])
            if fi >= 1:
                dq_prev = _motor_vel_row(reference, velocities_table[fi - 1])
                ddq = (dq - dq_prev) / dt
            else:
                ddq = np.zeros(29)
        else:
            q_prev = _row_to_q29(reference, jp[fi - 1])
            dq = (q - q_prev) / dt
            if fi >= 2:
                q_prev2 = _row_to_q29(reference, jp[fi - 2])
                ddq = (q - 2 * q_prev + q_prev2) / (dt**2)
            else:
                ddq = np.zeros(29)

        tau = pin.rnea(model, data, q, dq, ddq)
        for mi in range(29):
            lim = bundle_for_motor_index(mi).max_tau
            if abs(float(tau[mi])) > lim + 1e-3:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="torque_rnea_high",
                        message=f"|tau| from RNEA exceeds actuator cap (joint {mi})",
                        frame_index=fi,
                        motor_index=mi,
                        detail={"tau": float(tau[mi]), "limit_nm": lim},
                    )
                )

    err = any(i.severity == "error" for i in issues)
    return MotionValidationReport(ok=not err, issues=issues, pinocchio_used=True)
