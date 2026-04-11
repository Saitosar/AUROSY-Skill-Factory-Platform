"""
Headless MuJoCo playback for ReferenceTrajectory v1.

Dynamic mode uses the same PD law as unitree_mujoco UnitreeSdk2Bridge.LowCmdHandler:
  ctrl_i = kp*(q_des - q_pos_sens) + kd*(dq_des - q_vel_sens)

Kinematic mode sets hinge qpos from the trajectory and calls mj_forward only (no mj_step).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

import mujoco

from core_control.joint_controller import JointController

from skill_foundry_sim.trajectory_sampler import sample_trajectory_at_times

PlaybackMode = Literal["dynamic", "kinematic"]


def _motor_joint_qpos_adrs(model: mujoco.MjModel) -> list[int]:
    """qpos address for each actuator's joint (hinge), motor index 0..nu-1."""
    nu = model.nu
    out: list[int] = []
    for i in range(nu):
        base = JointController.JOINT_MAP[i]
        jname = f"{base}_joint"
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, jname)
        if jid < 0:
            raise RuntimeError(f"joint not found in MJCF: {jname}")
        adr = int(model.jnt_qposadr[jid])
        out.append(adr)
    return out


@dataclass
class PlaybackConfig:
    """Configuration for headless playback."""

    mjcf_path: str
    sim_dt: float
    mode: PlaybackMode = "dynamic"
    kp: float = 150.0
    kd: float = 5.0
    seed: int = 0
    max_steps: int | None = None
    """If None, run until reference duration (last sample time)."""


@dataclass
class PlaybackLog:
    """Arrays suitable for np.savez / comparison."""

    time_s: np.ndarray
    motor_q: np.ndarray
    motor_dq: np.ndarray  # measured joint velocity per motor (same index order as motor_q)
    reference_motor_q: np.ndarray  # interpolated reference targets, motor index order (for dataset ref)
    ctrl: np.ndarray
    meta: dict[str, Any] = field(default_factory=dict)


def run_headless_playback(
    reference: dict[str, Any],
    config: PlaybackConfig,
) -> PlaybackLog:
    """
    Run headless simulation and return a deterministic log for reproducibility checks.

    Parameters
    ----------
    reference
        Validated ReferenceTrajectory v1 dict.
    config
        Playback configuration (MJCF path, dt, mode, PD gains, seed).
    """
    np.random.seed(config.seed)

    joint_positions = reference["joint_positions"]
    frequency_hz = float(reference["frequency_hz"])
    joint_order = reference["joint_order"]
    joint_velocities = reference.get("joint_velocities")

    t_samples = len(joint_positions)
    t_end = (t_samples - 1) / frequency_hz
    if config.max_steps is not None:
        n_steps = int(config.max_steps)
    else:
        n_steps = int(np.ceil(t_end / config.sim_dt)) + 1

    times = np.arange(n_steps, dtype=np.float64) * config.sim_dt
    q_cols, dq_cols = sample_trajectory_at_times(
        joint_positions,
        frequency_hz,
        times,
        joint_velocities=joint_velocities,
    )

    mj_model = mujoco.MjModel.from_xml_path(config.mjcf_path)
    mj_model.opt.timestep = config.sim_dt
    mj_data = mujoco.MjData(mj_model)

    nu = mj_model.nu
    if nu != 29:
        raise ValueError(f"expected 29 actuators for G1 29DoF profile, got nu={nu}")

    mujoco.mj_resetData(mj_model, mj_data)

    motor_q_log = np.zeros((n_steps, nu), dtype=np.float64)
    motor_dq_log = np.zeros((n_steps, nu), dtype=np.float64)
    ref_q_motor_log = np.zeros((n_steps, nu), dtype=np.float64)
    ctrl_log = np.zeros((n_steps, nu), dtype=np.float64)
    time_log = np.zeros(n_steps, dtype=np.float64)

    def _fill_ref_targets(k: int) -> None:
        row_q = q_cols[k]
        for col, jid_str in enumerate(joint_order):
            mi = int(str(jid_str))
            ref_q_motor_log[k, mi] = row_q[col]

    if config.mode == "dynamic":
        for k in range(n_steps):
            _fill_ref_targets(k)
            q_des = mj_data.sensordata[:nu].copy()
            dq_des = mj_data.sensordata[nu : 2 * nu].copy()
            row_q = q_cols[k]
            row_dq = dq_cols[k]
            for col, jid_str in enumerate(joint_order):
                mi = int(str(jid_str))
                q_des[mi] = row_q[col]
                dq_des[mi] = row_dq[col]

            for i in range(nu):
                q_m = mj_data.sensordata[i]
                dq_m = mj_data.sensordata[nu + i]
                mj_data.ctrl[i] = config.kp * (q_des[i] - q_m) + config.kd * (dq_des[i] - dq_m)

            ctrl_log[k] = mj_data.ctrl.copy()
            mujoco.mj_step(mj_model, mj_data)
            time_log[k] = mj_data.time
            motor_q_log[k] = mj_data.sensordata[:nu].copy()
            motor_dq_log[k] = mj_data.sensordata[nu : 2 * nu].copy()

    elif config.mode == "kinematic":
        qpos_adrs = _motor_joint_qpos_adrs(mj_model)
        for k in range(n_steps):
            _fill_ref_targets(k)
            t_k = k * config.sim_dt
            time_log[k] = t_k
            row_q = q_cols[k]
            row_dq = dq_cols[k]
            for col, jid_str in enumerate(joint_order):
                mi = int(str(jid_str))
                adr = qpos_adrs[mi]
                mj_data.qpos[adr] = row_q[col]
                motor_dq_log[k, mi] = row_dq[col]
            mujoco.mj_forward(mj_model, mj_data)
            motor_q_log[k] = mj_data.sensordata[:nu].copy()
            ctrl_log[k] = 0.0
    else:
        raise ValueError(f"unknown mode: {config.mode}")

    meta = {
        "mujoco_version": mujoco.__version__,
        "mjcf_path": config.mjcf_path,
        "sim_dt": config.sim_dt,
        "mode": config.mode,
        "kp": config.kp,
        "kd": config.kd,
        "seed": config.seed,
        "frequency_hz": frequency_hz,
        "reference_root_model": reference.get("root_model"),
    }

    return PlaybackLog(
        time_s=time_log,
        motor_q=motor_q_log,
        motor_dq=motor_dq_log,
        reference_motor_q=ref_q_motor_log,
        ctrl=ctrl_log,
        meta=meta,
    )
