"""Self-collision sampling using MuJoCo contact detection (matches Skill Foundry playback)."""

from __future__ import annotations

from typing import Any

import mujoco
import numpy as np

from core_control.joint_controller import JointController
from skill_foundry_validation.report import MotionValidationReport, ValidationIssue


def _motor_joint_qpos_adrs(model: mujoco.MjModel) -> list[int]:
    """qpos address for each actuator's joint (hinge), motor index 0..28."""
    out: list[int] = []
    for i in range(29):
        base = JointController.JOINT_MAP[i]
        jname = f"{base}_joint"
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, jname)
        if jid < 0:
            raise RuntimeError(f"joint not found in MJCF: {jname}")
        out.append(int(model.jnt_qposadr[jid]))
    return out


def _row_to_motor_q(row: list[float] | Any, joint_order: list[str]) -> np.ndarray:
    arr = np.asarray(row, dtype=np.float64).ravel()
    q = np.zeros(29, dtype=np.float64)
    order_map = {str(k): i for i, k in enumerate(joint_order)}
    for mi in range(29):
        key = str(mi)
        if key not in order_map:
            raise ValueError(f"joint_order missing key {key}")
        ci = order_map[key]
        if ci >= len(arr):
            raise ValueError("joint_positions row shorter than joint_order")
        q[mi] = float(arr[ci])
    return q


def validate_self_collision_mujoco(
    reference: dict[str, Any],
    mjcf_path: str,
    *,
    frame_stride: int = 1,
    floor_geom_substrings: tuple[str, ...] = ("floor", "ground", "plane"),
) -> MotionValidationReport:
    """
    Sample trajectory at ``frame_stride`` and flag self-contacts (excluding floor).

    Uses ``scene_29dof``-style MJCF with free joint + hinge layout consistent with
    :func:`skill_foundry_sim.headless_playback._motor_joint_qpos_adrs`.
    """
    model = mujoco.MjModel.from_xml_path(mjcf_path)
    data = mujoco.MjData(model)

    joint_order = [str(x) for x in reference.get("joint_order", [])]
    jp = reference.get("joint_positions")
    if not isinstance(jp, list) or not joint_order:
        return MotionValidationReport(
            ok=False,
            collision_engine="mujoco",
            issues=[
                ValidationIssue(
                    severity="error",
                    code="collision_precheck",
                    message="invalid joint_order or joint_positions",
                )
            ],
        )

    try:
        qpos_adrs = _motor_joint_qpos_adrs(model)
    except RuntimeError as e:
        return MotionValidationReport(
            ok=False,
            collision_engine="mujoco",
            notes=[str(e)],
            issues=[
                ValidationIssue(
                    severity="error",
                    code="mjcf_joint_map",
                    message=str(e),
                )
            ],
        )

    issues: list[ValidationIssue] = []
    stride = max(1, int(frame_stride))

    for fi in range(0, len(jp), stride):
        row = jp[fi]
        if not isinstance(row, list):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="bad_row",
                    message=f"joint_positions[{fi}] must be list",
                    frame_index=fi,
                )
            )
            continue
        try:
            mq = _row_to_motor_q(row, joint_order)
        except ValueError as e:
            return MotionValidationReport(
                ok=False,
                collision_engine="mujoco",
                issues=[
                    ValidationIssue(
                        severity="error",
                        code="joint_map_row",
                        message=str(e),
                        frame_index=fi,
                    )
                ],
            )

        data.qpos[:] = model.qpos0
        for mi, adr in enumerate(qpos_adrs):
            data.qpos[adr] = mq[mi]

        mujoco.mj_forward(model, data)

        for ci in range(data.ncon):
            con = data.contact[ci]
            # Negative distance = penetration; ignore grazing / separating contacts
            if float(con.dist) >= 0.0:
                continue
            g1 = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, con.geom1)
            g2 = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, con.geom2)
            if g1 is None or g2 is None:
                continue
            floor_hit = any(s in g1.lower() for s in floor_geom_substrings) or any(
                s in g2.lower() for s in floor_geom_substrings
            )
            if floor_hit:
                continue
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="self_collision",
                    message=f"penetration {g1} <-> {g2}",
                    frame_index=fi,
                    detail={"geom1": g1, "geom2": g2, "dist": float(con.dist)},
                )
            )

    err = any(i.severity == "error" for i in issues)
    return MotionValidationReport(ok=not err, issues=issues, collision_engine="mujoco")
