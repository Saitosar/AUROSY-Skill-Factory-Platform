"""Inverse Kinematics correction for G1 trajectories using Pinocchio.

Adapts user-generated animations to match G1 robot kinematics (joint limits,
link lengths, reachability).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from skill_foundry_validation.paths import default_g1_urdf_path, default_package_dir_for_urdf


@dataclass
class IKCorrectionResult:
    """Result of IK-based trajectory correction."""

    corrected_positions: list[list[float]]
    frames_corrected: int
    total_corrections: int
    corrections_applied: list[dict[str, Any]] = field(default_factory=list)
    joint_limit_violations: int = 0


def _clamp_to_joint_limits(
    q: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Clamp joint angles to limits, return clamped array and violation count."""
    violations = 0
    q_clamped = q.copy()
    
    for i in range(len(q)):
        if q[i] < lower[i]:
            q_clamped[i] = lower[i]
            violations += 1
        elif q[i] > upper[i]:
            q_clamped[i] = upper[i]
            violations += 1
    
    return q_clamped, violations


def _row_to_q29(reference: dict[str, Any], row: list[float]) -> np.ndarray:
    """Convert trajectory row to motor-order array."""
    joint_order = [str(x) for x in reference["joint_order"]]
    order_map = {str(k): i for i, k in enumerate(joint_order)}
    arr = np.asarray(row, dtype=np.float64).ravel()
    q = np.zeros(29, dtype=np.float64)
    for mi in range(29):
        ci = order_map[str(mi)]
        q[mi] = float(arr[ci])
    return q


def _q29_to_row(motor_q: np.ndarray, joint_order: list[str]) -> list[float]:
    """Convert motor-order array back to trajectory row order."""
    order_map = {str(k): i for i, k in enumerate(joint_order)}
    row = [0.0] * len(joint_order)
    for mi in range(29):
        key = str(mi)
        ci = order_map[key]
        row[ci] = float(motor_q[mi])
    return row


def correct_joint_limits(
    reference: dict[str, Any],
    *,
    urdf_path: str | None = None,
) -> IKCorrectionResult:
    """Correct trajectory to respect G1 joint limits.
    
    Uses Pinocchio to load URDF and extract joint limits, then clamps
    all joint angles to valid ranges.
    
    Args:
        reference: ReferenceTrajectory dict
        urdf_path: Path to G1 URDF (uses default if None)
    
    Returns:
        IKCorrectionResult with corrected positions
    """
    try:
        import pinocchio as pin
    except ImportError as e:
        raise RuntimeError(
            "Pinocchio required for IK correction. Install with: pip install pin"
        ) from e
    
    path = urdf_path or str(default_g1_urdf_path())
    pkg = str(default_package_dir_for_urdf())
    
    model = pin.buildModelFromUrdf(path, package_dirs=[pkg])
    
    lower = model.lowerPositionLimit[:29]
    upper = model.upperPositionLimit[:29]
    
    joint_order = [str(x) for x in reference.get("joint_order", [])]
    jp = reference.get("joint_positions", [])
    
    corrected_positions: list[list[float]] = []
    frames_corrected = 0
    total_corrections = 0
    total_violations = 0
    corrections: list[dict[str, Any]] = []
    
    for fi, row in enumerate(jp):
        if not isinstance(row, list):
            corrected_positions.append(row)
            continue
        
        motor_q = _row_to_q29(reference, row)
        corrected_q, violations = _clamp_to_joint_limits(motor_q, lower, upper)
        
        if violations > 0:
            frames_corrected += 1
            total_violations += violations
            
            for mi in range(29):
                if motor_q[mi] != corrected_q[mi]:
                    total_corrections += 1
                    corrections.append({
                        "frame_index": fi,
                        "joint": mi,
                        "original": float(motor_q[mi]),
                        "corrected": float(corrected_q[mi]),
                        "limit_lower": float(lower[mi]),
                        "limit_upper": float(upper[mi]),
                    })
        
        corrected_row = _q29_to_row(corrected_q, joint_order)
        corrected_positions.append(corrected_row)
    
    return IKCorrectionResult(
        corrected_positions=corrected_positions,
        frames_corrected=frames_corrected,
        total_corrections=total_corrections,
        corrections_applied=corrections,
        joint_limit_violations=total_violations,
    )


def solve_ik_for_end_effector(
    model: Any,
    data: Any,
    target_position: np.ndarray,
    frame_id: int,
    q_init: np.ndarray,
    *,
    max_iterations: int = 100,
    tolerance: float = 1e-4,
    step_size: float = 0.1,
) -> tuple[np.ndarray, bool]:
    """Solve IK for a single end-effector target.
    
    Uses damped least squares (Levenberg-Marquardt style) IK.
    
    Args:
        model: Pinocchio model
        data: Pinocchio data
        target_position: Target 3D position for end-effector
        frame_id: Pinocchio frame ID for end-effector
        q_init: Initial joint configuration
        max_iterations: Max solver iterations
        tolerance: Position error tolerance (meters)
        step_size: IK step size
    
    Returns:
        Tuple of (solution_q, converged)
    """
    import pinocchio as pin
    
    q = q_init.copy()
    damping = 1e-6
    
    for _ in range(max_iterations):
        pin.forwardKinematics(model, data, q)
        pin.updateFramePlacements(model, data)
        
        current_pos = data.oMf[frame_id].translation
        error = target_position - current_pos
        
        if np.linalg.norm(error) < tolerance:
            return q, True
        
        J = pin.computeFrameJacobian(
            model, data, q, frame_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED
        )[:3, :]
        
        JJt = J @ J.T + damping * np.eye(3)
        dq = J.T @ np.linalg.solve(JJt, error)
        
        q = pin.integrate(model, q, step_size * dq)
        
        q = np.clip(q, model.lowerPositionLimit, model.upperPositionLimit)
    
    return q, False


def correct_trajectory_ik(
    reference: dict[str, Any],
    *,
    urdf_path: str | None = None,
    end_effector_frames: list[str] | None = None,
    target_positions: dict[int, dict[str, np.ndarray]] | None = None,
) -> IKCorrectionResult:
    """Correct trajectory using full IK solving.
    
    This is a more advanced correction that can adjust joint angles to
    achieve specific end-effector positions while respecting joint limits.
    
    Args:
        reference: ReferenceTrajectory dict
        urdf_path: Path to G1 URDF
        end_effector_frames: Frame names to track (e.g., ["left_hand", "right_hand"])
        target_positions: Dict mapping frame_index -> {frame_name: target_pos}
    
    Returns:
        IKCorrectionResult with IK-corrected positions
    """
    try:
        import pinocchio as pin
    except ImportError as e:
        raise RuntimeError(
            "Pinocchio required for IK correction. Install with: pip install pin"
        ) from e
    
    limit_result = correct_joint_limits(reference, urdf_path=urdf_path)
    
    if not target_positions:
        return limit_result
    
    path = urdf_path or str(default_g1_urdf_path())
    pkg = str(default_package_dir_for_urdf())
    
    model = pin.buildModelFromUrdf(path, package_dirs=[pkg])
    data = model.createData()
    
    joint_order = [str(x) for x in reference.get("joint_order", [])]
    corrected_positions = limit_result.corrected_positions.copy()
    
    frames_corrected = limit_result.frames_corrected
    total_corrections = limit_result.total_corrections
    corrections = limit_result.corrections_applied.copy()
    
    for fi, targets in target_positions.items():
        if fi >= len(corrected_positions):
            continue
        
        row = corrected_positions[fi]
        motor_q = _row_to_q29(reference, row)
        
        q_full = np.zeros(model.nq)
        q_full[:29] = motor_q
        
        for frame_name, target_pos in targets.items():
            frame_id = model.getFrameId(frame_name)
            if frame_id < 0:
                continue
            
            q_solved, converged = solve_ik_for_end_effector(
                model, data, target_pos, frame_id, q_full
            )
            
            if converged:
                motor_q = q_solved[:29]
                frames_corrected += 1
                total_corrections += 1
                corrections.append({
                    "frame_index": fi,
                    "type": "ik_solve",
                    "end_effector": frame_name,
                    "converged": True,
                })
        
        corrected_row = _q29_to_row(motor_q, joint_order)
        corrected_positions[fi] = corrected_row
    
    return IKCorrectionResult(
        corrected_positions=corrected_positions,
        frames_corrected=frames_corrected,
        total_corrections=total_corrections,
        corrections_applied=corrections,
        joint_limit_violations=limit_result.joint_limit_violations,
    )


def correct_reference_trajectory(
    reference: dict[str, Any],
    urdf_path: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience wrapper that returns a corrected ReferenceTrajectory dict.
    
    Args:
        reference: Original ReferenceTrajectory
        urdf_path: Path to G1 URDF
        **kwargs: Passed to correct_joint_limits or correct_trajectory_ik
    
    Returns:
        New ReferenceTrajectory dict with corrected joint_positions
    """
    result = correct_joint_limits(reference, urdf_path=urdf_path)
    
    corrected = {**reference}
    corrected["joint_positions"] = result.corrected_positions
    corrected["_ik_metadata"] = {
        "frames_corrected": result.frames_corrected,
        "total_corrections": result.total_corrections,
        "joint_limit_violations": result.joint_limit_violations,
        "corrections_applied": result.corrections_applied,
    }
    
    return corrected
