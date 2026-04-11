"""Align DemonstrationDataset v1 steps to RL observation space (Phase 3.3 BC).

Playback logs state after each ``mj_step`` at simulation time ``(step_index + 1) * sim_dt``;
``sampling_hz`` equals ``1 / sim_dt``. See :mod:`skill_foundry_sim.headless_playback`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from skill_foundry_phase0.contract_validator import validate_demonstration_dataset_dict
from skill_foundry_rl.obs_schema import RL_OBS_DIM_BASE, rl_obs_dim
from skill_foundry_sim.trajectory_sampler import sample_trajectory_at_times

logger = logging.getLogger(__name__)

NU = 29
DEMO_OBS_DIM = 58


def demo_step_time_s(step_index: int, sampling_hz: float) -> float:
    """Simulation time (seconds) for the observation recorded at demo step ``step_index``."""
    if sampling_hz <= 0:
        raise ValueError("sampling_hz must be positive")
    return float(step_index + 1) / float(sampling_hz)


def build_q_ref_motor(
    row_q: np.ndarray,
    motor_q: np.ndarray,
    joint_order: list[Any],
) -> np.ndarray:
    """Same construction as :meth:`G1TrackingEnv._build_q_ref_motor`."""
    q_ref = motor_q.astype(np.float64, copy=True)
    for col, jid_str in enumerate(joint_order):
        mi = int(str(jid_str))
        q_ref[mi] = float(row_q[col])
    return q_ref


def interpolated_reference_row_q(reference: dict[str, Any], episode_time_s: float) -> np.ndarray:
    """One row of interpolated joint reference (length D) at ``episode_time_s``."""
    joint_positions = reference["joint_positions"]
    frequency_hz = float(reference["frequency_hz"])
    joint_velocities = reference.get("joint_velocities")
    times = np.array([episode_time_s], dtype=np.float64)
    q_cols, _dq = sample_trajectory_at_times(
        joint_positions,
        frequency_hz,
        times,
        joint_velocities=joint_velocities,
    )
    return q_cols[0].astype(np.float64)


def rl_obs_from_demo_step(
    obs_58: np.ndarray,
    reference: dict[str, Any],
    episode_time_s: float,
) -> np.ndarray:
    """
    Build ``skill_foundry_rl_tracking_v1`` observation (87-D, no IMU) from a 58-D demo ``obs``.

    Parameters
    ----------
    obs_58
        Concatenation of motor positions and velocities (29 + 29).
    reference
        Validated ReferenceTrajectory v1 dict (``joint_positions``, ``frequency_hz``, ``joint_order``).
    episode_time_s
        Time used for interpolating reference rows (must match playback / env clock).
    """
    o = np.asarray(obs_58, dtype=np.float64).ravel()
    if o.size != DEMO_OBS_DIM:
        raise ValueError(f"expected obs length {DEMO_OBS_DIM}, got {o.size}")

    joint_order = reference["joint_order"]
    motor_q = o[:NU]
    motor_dq = o[NU:DEMO_OBS_DIM]
    row_q = interpolated_reference_row_q(reference, episode_time_s)
    q_ref = build_q_ref_motor(row_q, motor_q, joint_order)
    err = motor_q - q_ref
    return np.concatenate([motor_q, motor_dq, err], axis=0).astype(np.float64)


def _check_optional_ref_step(
    step: dict[str, Any],
    q_ref_computed: np.ndarray,
    *,
    step_label: str,
    atol: float,
) -> None:
    ref = step.get("ref")
    if ref is None:
        return
    arr = np.asarray(ref, dtype=np.float64).ravel()
    if arr.size != NU:
        logger.warning(
            "demo %s: optional ref length %s (expected %s); skip consistency check",
            step_label,
            arr.size,
            NU,
        )
        return
    delta = float(np.max(np.abs(arr - q_ref_computed)))
    if delta > atol:
        logger.warning(
            "demo %s: ref vs interpolated reference max abs diff %.6g (atol %.6g)",
            step_label,
            delta,
            atol,
        )


def load_demonstration_dataset(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    errs = validate_demonstration_dataset_dict(raw)
    if errs:
        raise ValueError("invalid demonstration dataset:\n" + "\n".join(errs))
    return raw


def build_bc_dataset_arrays(
    demonstration: dict[str, Any],
    reference: dict[str, Any],
    *,
    ref_check_atol: float = 1e-3,
    include_imu: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """
    Stack offline BC samples: RL observations and **normalized residual** targets (zeros for ref-only demos).

    Returns
    -------
    obs
        Shape (N, D) with D = :func:`rl_obs_dim` (``include_imu`` must be False; IMU not in demos).
    actions
        Shape (N, 29), targets in [-1, 1] — default zeros (expert follows reference without residual).
    info
        Metadata: step counts, warnings count.
    """
    if include_imu:
        raise ValueError(
            "BC pretrain does not support include_imu_in_obs=True (demonstrations lack IMU); "
            "set env.include_imu_in_obs to false when using bc."
        )

    d_obs = rl_obs_dim(include_imu=False)
    if d_obs != RL_OBS_DIM_BASE:
        raise RuntimeError("unexpected base RL obs dim")

    sampling_hz = float(demonstration["sampling_hz"])
    rows_obs: list[np.ndarray] = []
    rows_act: list[np.ndarray] = []

    total_steps = 0

    for e_idx, ep in enumerate(demonstration["episodes"]):
        steps = ep["steps"]
        for s_idx, step in enumerate(steps):
            total_steps += 1
            obs_raw = step["obs"]
            o58 = np.asarray(obs_raw, dtype=np.float64).ravel()
            if o58.size != DEMO_OBS_DIM:
                raise ValueError(
                    f"episode {e_idx} step {s_idx}: expected obs length {DEMO_OBS_DIM}, got {o58.size}"
                )

            t = demo_step_time_s(s_idx, sampling_hz)
            full = rl_obs_from_demo_step(o58, reference, t)
            if full.size != d_obs:
                raise RuntimeError("internal error: rl obs dim mismatch")

            motor_q = o58[:NU]
            row_q = interpolated_reference_row_q(reference, t)
            q_ref_m = build_q_ref_motor(row_q, motor_q, reference["joint_order"])
            _check_optional_ref_step(
                step,
                q_ref_m,
                step_label=f"ep{e_idx}/step{s_idx}",
                atol=ref_check_atol,
            )
            rows_obs.append(full)
            rows_act.append(np.zeros(NU, dtype=np.float64))

    obs_mat = np.stack(rows_obs, axis=0)
    act_mat = np.stack(rows_act, axis=0)
    info = {
        "num_episodes": len(demonstration["episodes"]),
        "num_steps": total_steps,
        "sampling_hz": sampling_hz,
    }
    return obs_mat, act_mat, info
