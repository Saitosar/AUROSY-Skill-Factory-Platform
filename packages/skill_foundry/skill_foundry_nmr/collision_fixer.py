"""Auto-correction of self-collisions in G1 trajectories using MuJoCo contact detection.

Iteratively adjusts joint angles when penetration is detected until collision-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import mujoco
import numpy as np

from core_control.joint_controller import JointController


@dataclass
class CollisionFixResult:
    """Result of collision fixing for a single frame or trajectory."""

    corrected_positions: list[list[float]]
    frames_fixed: int
    total_corrections: int
    fixes_applied: list[dict[str, Any]] = field(default_factory=list)


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
    """Convert trajectory row to motor-order array."""
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


def _motor_q_to_row(motor_q: np.ndarray, joint_order: list[str]) -> list[float]:
    """Convert motor-order array back to trajectory row order."""
    order_map = {str(k): i for i, k in enumerate(joint_order)}
    row = [0.0] * len(joint_order)
    for mi in range(29):
        key = str(mi)
        ci = order_map[key]
        row[ci] = float(motor_q[mi])
    return row


def _detect_collisions(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    floor_geom_substrings: tuple[str, ...] = ("floor", "ground", "plane"),
) -> list[dict[str, Any]]:
    """Detect self-collisions (excluding floor contacts)."""
    collisions = []
    for ci in range(data.ncon):
        con = data.contact[ci]
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
        collisions.append({
            "geom1": g1,
            "geom2": g2,
            "dist": float(con.dist),
            "pos": con.pos.copy(),
            "frame": con.frame.copy(),
        })
    return collisions


def _get_joints_for_geom(geom_name: str) -> list[int]:
    """Map geom name to relevant motor indices for correction.
    
    This is a heuristic mapping based on G1 body structure.
    """
    geom_lower = geom_name.lower()
    
    left_arm_joints = [13, 14, 15, 16, 17, 18, 19]
    right_arm_joints = [20, 21, 22, 23, 24, 25, 26]
    left_leg_joints = [0, 1, 2, 3, 4, 5]
    right_leg_joints = [6, 7, 8, 9, 10, 11]
    waist_joints = [12]
    head_joints = [27, 28]
    
    if "left" in geom_lower and ("arm" in geom_lower or "hand" in geom_lower or "elbow" in geom_lower or "shoulder" in geom_lower):
        return left_arm_joints
    if "right" in geom_lower and ("arm" in geom_lower or "hand" in geom_lower or "elbow" in geom_lower or "shoulder" in geom_lower):
        return right_arm_joints
    if "left" in geom_lower and ("leg" in geom_lower or "foot" in geom_lower or "knee" in geom_lower or "hip" in geom_lower or "ankle" in geom_lower):
        return left_leg_joints
    if "right" in geom_lower and ("leg" in geom_lower or "foot" in geom_lower or "knee" in geom_lower or "hip" in geom_lower or "ankle" in geom_lower):
        return right_leg_joints
    if "torso" in geom_lower or "pelvis" in geom_lower or "waist" in geom_lower:
        return waist_joints
    if "head" in geom_lower:
        return head_joints
    
    return []


def _fix_frame_collisions(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    qpos_adrs: list[int],
    motor_q: np.ndarray,
    *,
    max_iterations: int = 50,
    step_size: float = 0.02,
    min_step: float = 0.001,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Fix collisions for a single frame using gradient-based correction.
    
    Returns corrected motor_q and list of fixes applied.
    """
    fixes = []
    q_current = motor_q.copy()
    
    for iteration in range(max_iterations):
        data.qpos[:] = model.qpos0
        for mi, adr in enumerate(qpos_adrs):
            data.qpos[adr] = q_current[mi]
        mujoco.mj_forward(model, data)
        
        collisions = _detect_collisions(model, data)
        if not collisions:
            break
        
        for col in collisions:
            joints_g1 = _get_joints_for_geom(col["geom1"])
            joints_g2 = _get_joints_for_geom(col["geom2"])
            
            affected_joints = list(set(joints_g1 + joints_g2))
            if not affected_joints:
                continue
            
            penetration = abs(col["dist"])
            correction_magnitude = min(step_size, penetration * 0.5)
            correction_magnitude = max(correction_magnitude, min_step)
            
            for ji in affected_joints:
                direction = 1.0 if np.random.random() > 0.5 else -1.0
                
                q_test_pos = q_current.copy()
                q_test_pos[ji] += direction * correction_magnitude
                
                data.qpos[:] = model.qpos0
                for mi, adr in enumerate(qpos_adrs):
                    data.qpos[adr] = q_test_pos[mi]
                mujoco.mj_forward(model, data)
                collisions_pos = _detect_collisions(model, data)
                
                q_test_neg = q_current.copy()
                q_test_neg[ji] -= direction * correction_magnitude
                
                data.qpos[:] = model.qpos0
                for mi, adr in enumerate(qpos_adrs):
                    data.qpos[adr] = q_test_neg[mi]
                mujoco.mj_forward(model, data)
                collisions_neg = _detect_collisions(model, data)
                
                if len(collisions_pos) < len(collisions):
                    q_current = q_test_pos
                    fixes.append({
                        "iteration": iteration,
                        "joint": ji,
                        "delta": direction * correction_magnitude,
                        "collision": f"{col['geom1']} <-> {col['geom2']}",
                    })
                    break
                elif len(collisions_neg) < len(collisions):
                    q_current = q_test_neg
                    fixes.append({
                        "iteration": iteration,
                        "joint": ji,
                        "delta": -direction * correction_magnitude,
                        "collision": f"{col['geom1']} <-> {col['geom2']}",
                    })
                    break
    
    return q_current, fixes


def fix_self_collisions(
    reference: dict[str, Any],
    mjcf_path: str,
    *,
    max_iterations_per_frame: int = 50,
    step_size: float = 0.02,
    frame_stride: int = 1,
) -> CollisionFixResult:
    """Fix self-collisions in a ReferenceTrajectory.
    
    Iteratively adjusts joint angles when penetration is detected.
    
    Args:
        reference: ReferenceTrajectory dict with joint_positions and joint_order
        mjcf_path: Path to G1 MJCF scene file
        max_iterations_per_frame: Max correction iterations per frame
        step_size: Initial step size for joint angle correction (radians)
        frame_stride: Process every Nth frame (1 = all frames)
    
    Returns:
        CollisionFixResult with corrected positions and fix statistics
    """
    model = mujoco.MjModel.from_xml_path(mjcf_path)
    data = mujoco.MjData(model)
    
    joint_order = [str(x) for x in reference.get("joint_order", [])]
    jp = reference.get("joint_positions")
    
    if not isinstance(jp, list) or not joint_order:
        raise ValueError("Invalid reference: missing joint_order or joint_positions")
    
    qpos_adrs = _motor_joint_qpos_adrs(model)
    
    corrected_positions: list[list[float]] = []
    frames_fixed = 0
    total_corrections = 0
    all_fixes: list[dict[str, Any]] = []
    
    prev_motor_q: np.ndarray | None = None
    
    for fi in range(len(jp)):
        row = jp[fi]
        if not isinstance(row, list):
            corrected_positions.append(row)
            continue
        
        motor_q = _row_to_motor_q(row, joint_order)
        
        if fi % frame_stride == 0:
            data.qpos[:] = model.qpos0
            for mi, adr in enumerate(qpos_adrs):
                data.qpos[adr] = motor_q[mi]
            mujoco.mj_forward(model, data)
            
            collisions = _detect_collisions(model, data)
            
            if collisions:
                corrected_q, fixes = _fix_frame_collisions(
                    model,
                    data,
                    qpos_adrs,
                    motor_q,
                    max_iterations=max_iterations_per_frame,
                    step_size=step_size,
                )
                
                if fixes:
                    frames_fixed += 1
                    total_corrections += len(fixes)
                    for fix in fixes:
                        fix["frame_index"] = fi
                    all_fixes.extend(fixes)
                
                motor_q = corrected_q
        
        if prev_motor_q is not None and fi % frame_stride != 0:
            alpha = (fi % frame_stride) / frame_stride
            motor_q = (1 - alpha) * prev_motor_q + alpha * motor_q
        
        if fi % frame_stride == 0:
            prev_motor_q = motor_q.copy()
        
        corrected_row = _motor_q_to_row(motor_q, joint_order)
        corrected_positions.append(corrected_row)
    
    return CollisionFixResult(
        corrected_positions=corrected_positions,
        frames_fixed=frames_fixed,
        total_corrections=total_corrections,
        fixes_applied=all_fixes,
    )


def fix_reference_trajectory(
    reference: dict[str, Any],
    mjcf_path: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience wrapper that returns a corrected ReferenceTrajectory dict.
    
    Args:
        reference: Original ReferenceTrajectory
        mjcf_path: Path to G1 MJCF scene
        **kwargs: Passed to fix_self_collisions
    
    Returns:
        New ReferenceTrajectory dict with corrected joint_positions
    """
    result = fix_self_collisions(reference, mjcf_path, **kwargs)
    
    corrected = {**reference}
    corrected["joint_positions"] = result.corrected_positions
    corrected["_nmr_metadata"] = {
        "frames_fixed": result.frames_fixed,
        "total_corrections": result.total_corrections,
        "fixes_applied": result.fixes_applied,
    }
    
    return corrected
