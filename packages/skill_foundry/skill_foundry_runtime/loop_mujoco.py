"""Closed-loop policy + PD in MuJoCo (matches training observation timing)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import mujoco
import numpy as np

from skill_foundry_runtime.observation import (
    build_tracking_observation,
    imu_sensor_addresses,
    interpolated_reference_row_q_dq,
    read_imu_vector,
)
from skill_foundry_runtime.pd_control import residual_pd_torque
from skill_foundry_runtime.policy_sb3 import predict_action
from skill_foundry_runtime.safety import SafetyConfig, SafetyMonitor, actuator_joint_limits


@dataclass
class MujocoRunResult:
    steps: int
    stopped: bool
    stop_reason: str
    final_episode_time_s: float


def run_mujoco_skill_loop(
    *,
    mjcf_path: str,
    reference: dict[str, Any],
    manifest: dict[str, Any],
    policy: Any | None = None,
    max_steps: int | None = None,
    deterministic_policy: bool = True,
    min_base_height: float = 0.35,
    safety_cfg: SafetyConfig | None = None,
    action_fn: Callable[[np.ndarray], np.ndarray] | None = None,
) -> MujocoRunResult:
    """
    Run one episode: same obs timing as :class:`G1TrackingEnv` (obs at ``episode_time``
    after each step; initial obs at 0).

    Provide ``policy`` (SB3) or ``action_fn(obs) -> action`` for tests without a checkpoint.
    """
    if policy is None and action_fn is None:
        raise ValueError("run_mujoco_skill_loop requires policy or action_fn")

    ctrl = manifest["control"]
    dt_s = float(ctrl["dt_s"])
    kp = float(ctrl["kp"])
    kd = float(ctrl["kd"])
    delta_max = float(manifest["action"]["residual_scale_rad"])
    joint_order = list(manifest["joint_order"])

    joint_positions = reference["joint_positions"]
    freq = float(reference["frequency_hz"])
    t_max = (len(joint_positions) - 1) / freq

    include_imu = int(manifest["observation"]["vector_dim"]) > 87

    model = mujoco.MjModel.from_xml_path(mjcf_path)
    model.opt.timestep = dt_s
    data = mujoco.MjData(model)
    nu = int(model.nu)
    if nu != 29:
        raise ValueError(f"expected 29 actuators, got {nu}")

    imu_adrs: list[tuple[int, int]] = []
    if include_imu:
        imu_adrs = imu_sensor_addresses(model)

    q_low, q_high = actuator_joint_limits(model)
    safety = SafetyMonitor(q_low, q_high, safety_cfg or SafetyConfig())

    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)

    episode_time = 0.0
    motor_q = data.sensordata[:nu].copy()
    motor_dq = data.sensordata[nu : 2 * nu].copy()
    imu_vec = read_imu_vector(data, imu_adrs) if include_imu else None
    obs = build_tracking_observation(
        reference,
        joint_order,
        episode_time,
        motor_q,
        motor_dq,
        include_imu=include_imu,
        imu_vector=imu_vec,
    )

    steps = 0
    stopped = False
    stop_reason = ""

    while True:
        if max_steps is not None and steps >= max_steps:
            break
        if episode_time > t_max + 1e-9:
            break

        if action_fn is not None:
            action = action_fn(obs)
        else:
            action = predict_action(policy, obs, deterministic=deterministic_policy)

        row_q, row_dq = interpolated_reference_row_q_dq(reference, episode_time)
        tau, q_des, dq_des = residual_pd_torque(
            action,
            motor_q,
            motor_dq,
            row_q,
            row_dq,
            joint_order,
            delta_max=delta_max,
            kp=kp,
            kd=kd,
        )
        tau, stop, reason = safety.process(tau, motor_q, motor_dq, q_des, dq_des)
        if stop:
            stopped = True
            stop_reason = reason
            data.ctrl[:] = 0.0
            break

        data.ctrl[:] = tau
        mujoco.mj_step(model, data)
        episode_time += dt_s
        steps += 1

        height = float(data.qpos[2])
        if height < min_base_height:
            stopped = True
            stop_reason = "base height below min_base_height"
            data.ctrl[:] = 0.0
            break

        motor_q = data.sensordata[:nu].copy()
        motor_dq = data.sensordata[nu : 2 * nu].copy()
        imu_vec = read_imu_vector(data, imu_adrs) if include_imu else None
        obs = build_tracking_observation(
            reference,
            joint_order,
            episode_time,
            motor_q,
            motor_dq,
            include_imu=include_imu,
            imu_vector=imu_vec,
        )

    return MujocoRunResult(
        steps=steps,
        stopped=stopped,
        stop_reason=stop_reason,
        final_episode_time_s=episode_time,
    )
