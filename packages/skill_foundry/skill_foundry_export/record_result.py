"""Record policy rollout to JSON for UI feedback loop.

Runs a trained policy through MuJoCo simulation and records the actual
joint positions achieved, allowing users to see "what physics allowed"
vs "what they drew".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from skill_foundry_rl.g1_tracking_env import G1TrackingEnv, G1TrackingEnvConfig
from skill_foundry_sim.reference_loader import load_reference_trajectory_json


@dataclass
class RolloutResult:
    """Result of policy rollout recording."""

    joint_positions: list[list[float]]
    joint_order: list[str]
    frequency_hz: float
    total_steps: int
    total_reward: float
    episode_metrics: dict[str, Any] = field(default_factory=dict)
    policy_checkpoint: str = ""
    reference_sha256: str = ""


def record_policy_rollout(
    policy_path: Path,
    reference_path: Path,
    mjcf_path: str,
    *,
    env_config: G1TrackingEnvConfig | None = None,
    deterministic: bool = True,
) -> RolloutResult:
    """Run trained policy and record actual joint positions.
    
    Args:
        policy_path: Path to trained policy (.zip from SB3)
        reference_path: Path to reference trajectory JSON
        mjcf_path: Path to G1 MJCF scene
        env_config: Optional environment config (uses defaults if None)
        deterministic: Use deterministic policy inference
    
    Returns:
        RolloutResult with recorded positions and metrics
    """
    from stable_baselines3 import PPO
    
    ref_raw = load_reference_trajectory_json(reference_path)
    
    if env_config is None:
        env_config = G1TrackingEnvConfig(
            mjcf_path=mjcf_path,
            enable_collision_check=True,
            terminate_on_collision=False,
        )
    
    env = G1TrackingEnv(ref_raw, env_config)
    model = PPO.load(str(policy_path))
    
    recorded_positions: list[list[float]] = []
    total_reward = 0.0
    step_count = 0
    
    cumulative_metrics: dict[str, float] = {
        "r_track": 0.0,
        "r_alive": 0.0,
        "r_energy": 0.0,
        "r_jerk": 0.0,
        "r_collision": 0.0,
        "collision_count": 0,
        "fallen_count": 0,
    }
    
    obs, _ = env.reset()
    done = False
    
    while not done:
        action, _ = model.predict(obs, deterministic=deterministic)
        obs, reward, terminated, truncated, info = env.step(action)
        
        actual_q = env._data.sensordata[: env.nu].tolist()
        recorded_positions.append(actual_q)
        
        total_reward += reward
        step_count += 1
        
        for key in ["r_track", "r_alive", "r_energy", "r_jerk", "r_collision"]:
            if key in info:
                cumulative_metrics[key] += info[key]
        if info.get("has_collision"):
            cumulative_metrics["collision_count"] += info.get("collision_count", 1)
        if info.get("fallen"):
            cumulative_metrics["fallen_count"] += 1
        
        done = terminated or truncated
    
    joint_order = [str(x) for x in ref_raw.get("joint_order", [])]
    
    return RolloutResult(
        joint_positions=recorded_positions,
        joint_order=joint_order,
        frequency_hz=1.0 / env_config.sim_dt,
        total_steps=step_count,
        total_reward=total_reward,
        episode_metrics=cumulative_metrics,
        policy_checkpoint=str(policy_path),
    )


def rollout_to_reference_json(
    result: RolloutResult,
    original_reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert RolloutResult to ReferenceTrajectory JSON format.
    
    Args:
        result: RolloutResult from record_policy_rollout
        original_reference: Original reference for metadata inheritance
    
    Returns:
        ReferenceTrajectory dict ready for JSON serialization
    """
    output: dict[str, Any] = {
        "joint_positions": result.joint_positions,
        "joint_order": result.joint_order,
        "frequency_hz": result.frequency_hz,
        "source": "rl_policy_rollout",
        "_rollout_metadata": {
            "total_steps": result.total_steps,
            "total_reward": result.total_reward,
            "policy_checkpoint": result.policy_checkpoint,
            "episode_metrics": result.episode_metrics,
        },
    }
    
    if original_reference:
        if "name" in original_reference:
            output["name"] = f"{original_reference['name']}_physics_corrected"
        if "description" in original_reference:
            output["description"] = (
                f"Physics-corrected version of: {original_reference.get('description', '')}"
            )
    
    return output


def record_and_save(
    policy_path: Path,
    reference_path: Path,
    mjcf_path: str,
    output_path: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience function: record rollout and save to JSON file.
    
    Args:
        policy_path: Path to trained policy
        reference_path: Path to reference trajectory
        mjcf_path: Path to MJCF scene
        output_path: Where to save result JSON
        **kwargs: Passed to record_policy_rollout
    
    Returns:
        The saved ReferenceTrajectory dict
    """
    ref_raw = load_reference_trajectory_json(reference_path)
    
    result = record_policy_rollout(
        policy_path=policy_path,
        reference_path=reference_path,
        mjcf_path=mjcf_path,
        **kwargs,
    )
    
    output_json = rollout_to_reference_json(result, original_reference=ref_raw)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_json, indent=2), encoding="utf-8")
    
    return output_json


def compare_trajectories(
    original: dict[str, Any],
    recorded: dict[str, Any],
) -> dict[str, Any]:
    """Compare original reference with recorded rollout.
    
    Useful for UI to show "what you drew" vs "what physics allowed".
    
    Returns:
        Comparison metrics including per-joint MSE, max deviation, etc.
    """
    orig_jp = np.array(original["joint_positions"])
    rec_jp = np.array(recorded["joint_positions"])
    
    min_len = min(len(orig_jp), len(rec_jp))
    orig_jp = orig_jp[:min_len]
    rec_jp = rec_jp[:min_len]
    
    diff = orig_jp - rec_jp
    
    per_joint_mse = np.mean(diff ** 2, axis=0).tolist()
    per_joint_max_dev = np.max(np.abs(diff), axis=0).tolist()
    overall_mse = float(np.mean(diff ** 2))
    overall_max_dev = float(np.max(np.abs(diff)))
    
    return {
        "frames_compared": min_len,
        "overall_mse": overall_mse,
        "overall_max_deviation_rad": overall_max_dev,
        "per_joint_mse": per_joint_mse,
        "per_joint_max_deviation_rad": per_joint_max_dev,
    }
