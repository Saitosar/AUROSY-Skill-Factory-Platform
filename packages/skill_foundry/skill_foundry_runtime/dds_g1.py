"""G1 low-level DDS: LowState → obs → policy → LowCmd (position PD in firmware)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from skill_foundry_runtime.observation import build_tracking_observation, interpolated_reference_row_q_dq
from skill_foundry_runtime.pd_control import residual_pd_torque
from skill_foundry_runtime.policy_sb3 import predict_action
from skill_foundry_runtime.g1_joint_limits import g1_29dof_motor_q_limits
from skill_foundry_runtime.safety import SafetyConfig, SafetyMonitor

G1_NUM_MOTOR = 29


@dataclass
class DDSRunConfig:
    network_interface: str | None = None
    """Pass to ``ChannelFactoryInitialize(0, iface)`` when set."""
    max_steps: int | None = None
    deterministic_policy: bool = True
    min_state_freshness_s: float = 0.1
    """Watchdog: abort if LowState is older than this (seconds)."""


def _motor_arrays_from_low_state(low_state: Any) -> tuple[np.ndarray, np.ndarray]:
    q = np.zeros(G1_NUM_MOTOR, dtype=np.float64)
    dq = np.zeros(G1_NUM_MOTOR, dtype=np.float64)
    for i in range(G1_NUM_MOTOR):
        q[i] = float(low_state.motor_state[i].q)
        dq[i] = float(low_state.motor_state[i].dq)
    return q, dq


def run_dds_g1_skill_loop(
    *,
    reference: dict[str, Any],
    manifest: dict[str, Any],
    policy: Any,
    cfg: DDSRunConfig | None = None,
    safety_cfg: SafetyConfig | None = None,
    action_fn: Callable[[np.ndarray], np.ndarray] | None = None,
) -> int:
    """
    WARNING: Use only on a cleared test stand with e-stop. Releases motion modes then
    publishes ``LowCmd`` at approximately ``manifest.control.dt_s`` intervals.

    Sends ``q``/``dq``/``kp``/``kd`` with ``tau=0`` so joint firmware applies PD to the
    residual reference (same targets as MuJoCo torque law at nominal gains).

    Returns number of control steps executed.

    Raises ``NotImplementedError`` when the manifest expects IMU observations (hardware
    mapping not implemented in this prototype).
    """
    from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher, ChannelSubscriber
    from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
    from unitree_sdk2py.utils.crc import CRC

    cfg = cfg or DDSRunConfig()
    ctrl = manifest["control"]
    dt_s = float(ctrl["dt_s"])
    kp_hw = float(ctrl["kp"])
    kd_hw = float(ctrl["kd"])
    delta_max = float(manifest["action"]["residual_scale_rad"])
    joint_order = list(manifest["joint_order"])
    include_imu = int(manifest["observation"]["vector_dim"]) > 87
    if include_imu:
        raise NotImplementedError(
            "IMU observations on hardware require mapping LowState.imu_state to "
            "MJCF sensor layout; extend dds_g1 or use MuJoCo."
        )

    joint_positions = reference["joint_positions"]
    freq = float(reference["frequency_hz"])
    t_max = (len(joint_positions) - 1) / freq

    if cfg.network_interface:
        ChannelFactoryInitialize(0, cfg.network_interface)
    else:
        ChannelFactoryInitialize(0)

    msc = MotionSwitcherClient()
    msc.SetTimeout(5.0)
    msc.Init()
    _status, result = msc.CheckMode()
    while result["name"]:
        msc.ReleaseMode()
        _status, result = msc.CheckMode()
        time.sleep(0.2)

    low_state_holder: dict[str, Any] = {"msg": None, "t": 0.0}

    def handler(msg: Any) -> None:
        low_state_holder["msg"] = msg
        low_state_holder["t"] = time.monotonic()

    subscriber = ChannelSubscriber("rt/lowstate", LowState_)
    subscriber.Init(handler, 10)
    publisher = ChannelPublisher("rt/lowcmd", LowCmd_)
    publisher.Init()

    deadline = time.monotonic() + 30.0
    while low_state_holder["msg"] is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if low_state_holder["msg"] is None:
        raise RuntimeError("no LowState (check interface and robot)")

    low_state = low_state_holder["msg"]
    mode_machine = int(low_state.mode_machine)

    crc = CRC()
    low_cmd = unitree_hg_msg_dds__LowCmd_()

    q_low, q_high = g1_29dof_motor_q_limits()
    safety = SafetyMonitor(q_low, q_high, safety_cfg or SafetyConfig())

    episode_time = 0.0
    steps = 0

    while episode_time <= t_max + 1e-9:
        if cfg.max_steps is not None and steps >= cfg.max_steps:
            break
        now = time.monotonic()
        if low_state_holder["msg"] is None:
            raise RuntimeError("LowState lost")
        if now - float(low_state_holder["t"]) > cfg.min_state_freshness_s:
            raise RuntimeError("LowState watchdog: state too stale")

        low_state = low_state_holder["msg"]
        motor_q, motor_dq = _motor_arrays_from_low_state(low_state)

        obs = build_tracking_observation(
            reference,
            joint_order,
            episode_time,
            motor_q,
            motor_dq,
            include_imu=False,
        )
        if action_fn is not None:
            action = action_fn(obs)
        else:
            action = predict_action(policy, obs, deterministic=cfg.deterministic_policy)

        row_q, row_dq = interpolated_reference_row_q_dq(reference, episode_time)
        _tau, q_des, dq_des = residual_pd_torque(
            action,
            motor_q,
            motor_dq,
            row_q,
            row_dq,
            joint_order,
            delta_max=delta_max,
            kp=kp_hw,
            kd=kd_hw,
        )
        _, stop, reason = safety.process(_tau, motor_q, motor_dq, q_des, dq_des)
        if stop:
            raise RuntimeError(f"safety stop: {reason}")

        low_cmd.mode_pr = 0
        low_cmd.mode_machine = mode_machine
        for i in range(G1_NUM_MOTOR):
            low_cmd.motor_cmd[i].mode = 1
            low_cmd.motor_cmd[i].tau = 0.0
            low_cmd.motor_cmd[i].q = float(q_des[i])
            low_cmd.motor_cmd[i].dq = float(dq_des[i])
            low_cmd.motor_cmd[i].kp = float(kp_hw)
            low_cmd.motor_cmd[i].kd = float(kd_hw)

        low_cmd.crc = crc.Crc(low_cmd)
        publisher.Write(low_cmd)

        time.sleep(dt_s)
        episode_time += dt_s
        steps += 1

    return steps
