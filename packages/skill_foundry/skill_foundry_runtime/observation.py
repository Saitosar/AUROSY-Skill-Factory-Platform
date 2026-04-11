"""Build RL observation vector matching :class:`G1TrackingEnv`."""

from __future__ import annotations

from typing import Any

import mujoco
import numpy as np

from skill_foundry_rl.obs_schema import IMU_SENSOR_NAMES
from skill_foundry_sim.trajectory_sampler import sample_trajectory_at_times


def interpolated_reference_row_q_dq(
    reference: dict[str, Any],
    episode_time_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    joint_positions = reference["joint_positions"]
    frequency_hz = float(reference["frequency_hz"])
    joint_velocities = reference.get("joint_velocities")
    times = np.array([episode_time_s], dtype=np.float64)
    q_cols, dq_cols = sample_trajectory_at_times(
        joint_positions,
        frequency_hz,
        times,
        joint_velocities=joint_velocities,
    )
    return q_cols[0].astype(np.float64), dq_cols[0].astype(np.float64)


def build_q_ref_motor(
    row_q: np.ndarray,
    motor_q: np.ndarray,
    joint_order: list[Any],
) -> np.ndarray:
    q_ref = np.asarray(motor_q, dtype=np.float64).copy()
    for col, jid_str in enumerate(joint_order):
        mi = int(str(jid_str))
        q_ref[mi] = float(row_q[col])
    return q_ref


def imu_sensor_addresses(model: mujoco.MjModel) -> list[tuple[int, int]]:
    adrs: list[tuple[int, int]] = []
    for name in IMU_SENSOR_NAMES:
        sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SENSOR, name)
        if sid < 0:
            raise RuntimeError(f"sensor not found in MJCF: {name}")
        adr = int(model.sensor_adr[sid])
        dim = int(model.sensor_dim[sid])
        adrs.append((adr, dim))
    return adrs


def read_imu_vector(data: mujoco.MjData, imu_adrs: list[tuple[int, int]]) -> np.ndarray:
    blocks: list[np.ndarray] = []
    for adr, dim in imu_adrs:
        blocks.append(np.array(data.sensordata[adr : adr + dim], dtype=np.float64))
    return np.concatenate(blocks)


def build_tracking_observation(
    reference: dict[str, Any],
    joint_order: list[Any],
    episode_time_s: float,
    motor_q: np.ndarray,
    motor_dq: np.ndarray,
    *,
    include_imu: bool = False,
    imu_vector: np.ndarray | None = None,
) -> np.ndarray:
    """
    Same layout as :meth:`skill_foundry_rl.g1_tracking_env.G1TrackingEnv._get_obs`
    for the given simulation time (post-step convention: ``episode_time_s`` matches
    env's ``_episode_time`` after each step).
    """
    q = np.asarray(motor_q, dtype=np.float64).ravel()
    dq = np.asarray(motor_dq, dtype=np.float64).ravel()
    row_q, _row_dq = interpolated_reference_row_q_dq(reference, episode_time_s)
    q_ref = build_q_ref_motor(row_q, q, joint_order)
    err = q - q_ref
    parts: list[np.ndarray] = [q, dq, err]
    if include_imu:
        if imu_vector is None:
            raise ValueError("include_imu=True requires imu_vector")
        parts.append(np.asarray(imu_vector, dtype=np.float64).ravel())
    return np.concatenate(parts).astype(np.float64)
