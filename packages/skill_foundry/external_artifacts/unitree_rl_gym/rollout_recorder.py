"""
Record joint trajectory rollout from Unitree pre-trained LSTM policy.

Based on unitree_rl_gym/deploy/deploy_mujoco/deploy_mujoco.py
Outputs intermediate .npz with joint positions over time.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
import torch


def get_gravity_orientation(quaternion: np.ndarray) -> np.ndarray:
    """Project gravity into body frame from quaternion (w,x,y,z)."""
    qw, qx, qy, qz = quaternion
    return np.array([
        2 * (-qz * qx + qw * qy),
        -2 * (qz * qy + qw * qx),
        1 - 2 * (qw * qw + qz * qz),
    ])


def pd_control(
    target_q: np.ndarray,
    q: np.ndarray,
    kp: np.ndarray,
    target_dq: np.ndarray,
    dq: np.ndarray,
    kd: np.ndarray,
) -> np.ndarray:
    """PD torque computation."""
    return (target_q - q) * kp + (target_dq - dq) * kd


def record_rollout(
    policy_path: Path,
    xml_path: Path,
    config: dict[str, Any],
    duration_s: float = 10.0,
    output_hz: float = 50.0,
) -> dict[str, Any]:
    """
    Run policy in MuJoCo and record joint positions.

    Returns dict with:
      - joint_positions: [T, num_actions] array
      - timestamps_s: [T] array
      - metadata: config and provenance info
    """
    simulation_dt = config["simulation_dt"]
    control_decimation = config["control_decimation"]
    kps = np.array(config["kps"], dtype=np.float32)
    kds = np.array(config["kds"], dtype=np.float32)
    default_angles = np.array(config["default_angles"], dtype=np.float32)
    ang_vel_scale = config["ang_vel_scale"]
    dof_pos_scale = config["dof_pos_scale"]
    dof_vel_scale = config["dof_vel_scale"]
    action_scale = config["action_scale"]
    cmd_scale = np.array(config["cmd_scale"], dtype=np.float32)
    num_actions = config["num_actions"]
    num_obs = config["num_obs"]
    cmd = np.array(config.get("cmd_init", [0.5, 0, 0]), dtype=np.float32)

    action = np.zeros(num_actions, dtype=np.float32)
    target_dof_pos = default_angles.copy()
    obs = np.zeros(num_obs, dtype=np.float32)

    m = mujoco.MjModel.from_xml_path(str(xml_path))
    d = mujoco.MjData(m)
    m.opt.timestep = simulation_dt

    policy = torch.jit.load(str(policy_path), map_location="cpu")
    policy.eval()

    total_steps = int(duration_s / simulation_dt)
    record_every = max(1, int(1.0 / (output_hz * simulation_dt)))

    positions_list: list[np.ndarray] = []
    timestamps_list: list[float] = []

    counter = 0
    for step in range(total_steps):
        tau = pd_control(target_dof_pos, d.qpos[7:7+num_actions], kps, np.zeros_like(kds), d.qvel[6:6+num_actions], kds)
        d.ctrl[:num_actions] = tau
        mujoco.mj_step(m, d)

        counter += 1
        if counter % control_decimation == 0:
            qj = d.qpos[7:7+num_actions]
            dqj = d.qvel[6:6+num_actions]
            quat = d.qpos[3:7]
            omega = d.qvel[3:6]

            qj_scaled = (qj - default_angles) * dof_pos_scale
            dqj_scaled = dqj * dof_vel_scale
            gravity_orientation = get_gravity_orientation(quat)
            omega_scaled = omega * ang_vel_scale

            period = 0.8
            count = counter * simulation_dt
            phase = count % period / period
            sin_phase = np.sin(2 * np.pi * phase)
            cos_phase = np.cos(2 * np.pi * phase)

            obs[:3] = omega_scaled
            obs[3:6] = gravity_orientation
            obs[6:9] = cmd * cmd_scale
            obs[9:9+num_actions] = qj_scaled
            obs[9+num_actions:9+2*num_actions] = dqj_scaled
            obs[9+2*num_actions:9+3*num_actions] = action
            obs[9+3*num_actions:9+3*num_actions+2] = np.array([sin_phase, cos_phase])

            obs_tensor = torch.from_numpy(obs).unsqueeze(0)
            with torch.no_grad():
                action = policy(obs_tensor).detach().numpy().squeeze()

            target_dof_pos = action * action_scale + default_angles

        if step % record_every == 0:
            positions_list.append(d.qpos[7:7+num_actions].copy())
            timestamps_list.append(step * simulation_dt)

    return {
        "joint_positions": np.array(positions_list),
        "timestamps_s": np.array(timestamps_list),
        "metadata": {
            "policy_path": str(policy_path),
            "xml_path": str(xml_path),
            "duration_s": duration_s,
            "output_hz": output_hz,
            "simulation_dt": simulation_dt,
            "control_decimation": control_decimation,
            "num_actions": num_actions,
            "default_angles": default_angles.tolist(),
            "cmd": cmd.tolist(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        },
    }


G1_CONFIG_12DOF = {
    "simulation_dt": 0.002,
    "control_decimation": 10,
    "kps": [100, 100, 100, 150, 40, 40, 100, 100, 100, 150, 40, 40],
    "kds": [2, 2, 2, 4, 2, 2, 2, 2, 2, 4, 2, 2],
    "default_angles": [-0.1, 0.0, 0.0, 0.3, -0.2, 0.0, -0.1, 0.0, 0.0, 0.3, -0.2, 0.0],
    "ang_vel_scale": 0.25,
    "dof_pos_scale": 1.0,
    "dof_vel_scale": 0.05,
    "action_scale": 0.25,
    "cmd_scale": [2.0, 2.0, 0.25],
    "num_actions": 12,
    "num_obs": 47,
    "cmd_init": [0.5, 0, 0],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Record rollout from Unitree LSTM policy")
    parser.add_argument("--policy", type=Path, default=Path(__file__).parent / "motion.pt")
    parser.add_argument("--xml", type=Path, help="Path to G1 MJCF scene.xml")
    parser.add_argument("--duration", type=float, default=10.0, help="Rollout duration in seconds")
    parser.add_argument("--hz", type=float, default=50.0, help="Output sampling rate")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output .npz path")
    args = parser.parse_args()

    if args.xml is None:
        repo_root = Path(__file__).resolve().parents[4]
        args.xml = repo_root / "unitree_mujoco" / "unitree_robots" / "g1" / "scene.xml"

    if not args.policy.is_file():
        raise FileNotFoundError(f"Policy not found: {args.policy}")
    if not args.xml.is_file():
        raise FileNotFoundError(f"MJCF not found: {args.xml}")

    print(f"Policy: {args.policy}")
    print(f"MJCF: {args.xml}")
    print(f"Duration: {args.duration}s @ {args.hz} Hz output")

    result = record_rollout(
        policy_path=args.policy,
        xml_path=args.xml,
        config=G1_CONFIG_12DOF,
        duration_s=args.duration,
        output_hz=args.hz,
    )

    out_path = args.output or args.policy.parent / "rollout_12dof.npz"
    np.savez_compressed(
        out_path,
        joint_positions=result["joint_positions"],
        timestamps_s=result["timestamps_s"],
    )
    meta_path = out_path.with_suffix(".meta.json")
    with meta_path.open("w") as f:
        json.dump(result["metadata"], f, indent=2)

    print(f"Saved: {out_path} ({result['joint_positions'].shape})")
    print(f"Metadata: {meta_path}")


if __name__ == "__main__":
    main()
