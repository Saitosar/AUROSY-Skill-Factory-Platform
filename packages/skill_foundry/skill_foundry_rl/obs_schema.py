"""Observation schema identifiers for RL training (Phase 3.2) — aligns with export manifest (Phase 4)."""

from __future__ import annotations

# Base layout: motor_q[29], motor_dq[29], (q_meas - q_ref)[29] — same joint order as playback / DemonstrationDataset motor index.
RL_OBS_SCHEMA_REF = "skill_foundry_rl_tracking_v1"
RL_OBS_DIM_BASE = 87  # 29 + 29 + 29
# Optional IMU block (imu_quat 4 + imu_gyro 3 + imu_acc 3) appended when include_imu_in_obs=True.
RL_OBS_IMU_EXTRA_DIM = 13
IMU_SENSOR_NAMES = ("imu_quat", "imu_gyro", "imu_acc")


def rl_obs_dim(*, include_imu: bool) -> int:
    """Flat observation size for G1TrackingEnv."""
    return RL_OBS_DIM_BASE + (RL_OBS_IMU_EXTRA_DIM if include_imu else 0)
