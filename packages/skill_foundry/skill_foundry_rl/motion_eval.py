"""AMP motion evaluation: metrics from rollouts vs reference, eval_motion.json contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from skill_foundry_phase0.contract_validator import validate_reference_trajectory_dict
from skill_foundry_sim.reference_loader import load_reference_trajectory_json

from skill_foundry_rl.amp_discriminator import AMPDiscriminator
from skill_foundry_rl.g1_tracking_env import G1TrackingEnv, g1_env_cfg_from_train_config
from skill_foundry_rl.obs_schema import rl_obs_dim
from skill_foundry_rl.reference_motion import ReferenceMotion, reference_motion_from_dict

EVAL_MOTION_SCHEMA_VERSION = "1.0"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def motor_labels_from_joint_order(joint_order: list[str]) -> list[str]:
    """Human-readable labels for 29 motors (prefer trajectory joint ids)."""
    out: list[str] = []
    for _mi in range(29):
        out.append(str(_mi))
    for col, jid in enumerate(joint_order):
        mi = int(str(jid))
        if 0 <= mi < 29:
            out[mi] = str(jid)
    return out


def compute_per_joint_mse(rollout_q: np.ndarray, ref_q: np.ndarray) -> tuple[np.ndarray, float]:
    """MSE per motor and mean (same length T, shape (T, 29))."""
    if rollout_q.shape != ref_q.shape:
        raise ValueError("rollout_q and ref_q must have identical shape")
    err = rollout_q.astype(np.float64) - ref_q.astype(np.float64)
    per_joint = np.mean(err**2, axis=0)
    return per_joint, float(np.mean(per_joint))


def compute_foot_sliding_proxy(motor_q: np.ndarray, dt: float) -> dict[str, Any] | None:
    """
    Heuristic foot sliding proxy without MuJoCo contact traces.

    Uses mean squared angular velocity of ankle pitch/roll motors (G1 motor indices
    4,5 and 10,11 in ``skill_foundry_retarget.G1_JOINT_ORDER``) as a cheap correlate
    of foot motion energy. Lower is generally better for stable standing/walking clips.
    """
    if motor_q.ndim != 2 or motor_q.shape[0] < 2 or motor_q.shape[1] < 12 or dt <= 0:
        return None
    idx = (4, 5, 10, 11)
    dq = np.diff(motor_q[:, idx], axis=0) / float(dt)
    msq = float(np.mean(np.sum(dq * dq, axis=1)))
    return {
        "method": "ankle_velocity_energy",
        "mean_sq_velocity": msq,
        "motor_indices": list(idx),
    }


def compute_velocity_mse(rollout_q: np.ndarray, ref_q: np.ndarray, dt: float) -> float | None:
    """Compare joint velocity finite differences (T-1 vectors)."""
    if dt <= 0 or rollout_q.shape[0] < 2:
        return None
    v_r = np.diff(rollout_q.astype(np.float64), axis=0) / dt
    v_e = np.diff(ref_q.astype(np.float64), axis=0) / dt
    n = min(v_r.shape[0], v_e.shape[0])
    if n < 1:
        return None
    return float(np.mean((v_r[:n] - v_e[:n]) ** 2))


def discriminator_realism_summary(
    disc: AMPDiscriminator,
    obs: np.ndarray,
    next_obs: np.ndarray,
    *,
    batch: int = 512,
) -> dict[str, Any]:
    """Mean AMP reward on transitions (same as training reward signal)."""
    import torch

    n = obs.shape[0]
    if n == 0:
        return {"mean_amp_reward": None, "count": 0}
    rewards: list[float] = []
    for start in range(0, n, batch):
        end = min(start + batch, n)
        o = torch.as_tensor(obs[start:end], dtype=torch.float32)
        on = torch.as_tensor(next_obs[start:end], dtype=torch.float32)
        r = disc.amp_reward(o, on)
        rewards.extend(r.cpu().numpy().tolist())
    arr = np.array(rewards, dtype=np.float64)
    return {
        "mean_amp_reward": float(arr.mean()),
        "std_amp_reward": float(arr.std()) if arr.size > 1 else 0.0,
        "count": int(n),
    }


def reference_motor_q_at_times(ref: ReferenceMotion, times_s: np.ndarray) -> np.ndarray:
    """Motor-order q (T, 29) at each time."""
    q_cols, dq_cols = ref.sample_joint_rows(times_s)
    q_m, _dq_m = ref.to_motor_rows(q_cols, dq_cols)
    return q_m.astype(np.float64)


@dataclass
class RolloutBatch:
    """Policy rollout slices for metrics."""

    times_s: np.ndarray  # (T,) — sim time after each step
    motor_q: np.ndarray  # (T, 29)
    obs: np.ndarray  # (T, obs_dim)
    next_obs: np.ndarray  # (T, obs_dim)


def collect_rollout(
    model: Any,
    env: G1TrackingEnv,
    *,
    max_steps: int,
    seed: int,
    deterministic: bool = True,
) -> RolloutBatch:
    """Roll out policy until truncate/terminate or max_steps."""
    obs, _info = env.reset(seed=seed)
    dt = float(env._cfg.sim_dt)
    times: list[float] = []
    qs: list[np.ndarray] = []
    obss: list[np.ndarray] = []
    next_obss: list[np.ndarray] = []

    for _ in range(max_steps):
        action, _ = model.predict(obs, deterministic=deterministic)
        next_obs, _reward, terminated, truncated, _info = env.step(action)
        t_next = float(env._episode_time)
        times.append(t_next)
        qs.append(np.asarray(next_obs[:29], dtype=np.float64))
        obss.append(np.asarray(obs, dtype=np.float64))
        next_obss.append(np.asarray(next_obs, dtype=np.float64))
        obs = next_obs
        if terminated or truncated:
            break

    if not times:
        return RolloutBatch(
            times_s=np.zeros((0,), dtype=np.float64),
            motor_q=np.zeros((0, 29), dtype=np.float64),
            obs=np.zeros((0, obs.shape[0]), dtype=np.float64),
            next_obs=np.zeros((0, obs.shape[0]), dtype=np.float64),
        )

    return RolloutBatch(
        times_s=np.asarray(times, dtype=np.float64),
        motor_q=np.stack(qs, axis=0),
        obs=np.stack(obss, axis=0),
        next_obs=np.stack(next_obss, axis=0),
    )


def build_eval_motion_report(
    *,
    reference_sha256: str,
    checkpoint: str,
    joint_order: list[str],
    rollout: RolloutBatch,
    ref: ReferenceMotion,
    sim_dt: float,
    discriminator_path: Path | None,
    amp_cfg: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble eval_motion.json dict (before writing)."""
    ref_q = reference_motor_q_at_times(ref, rollout.times_s)
    n = min(rollout.motor_q.shape[0], ref_q.shape[0])
    rq = rollout.motor_q[:n]
    rref = ref_q[:n]

    per_joint_arr, mean_mse = compute_per_joint_mse(rq, rref)
    labels = motor_labels_from_joint_order(joint_order)
    per_joint_mse = {labels[i]: float(per_joint_arr[i]) for i in range(29)}

    vel_mse = compute_velocity_mse(rq, rref, sim_dt)
    foot_sliding = compute_foot_sliding_proxy(rq, sim_dt)

    disc_summary: dict[str, Any] | None = None
    if discriminator_path is not None and discriminator_path.is_file() and rollout.obs.shape[0] > 0:
        import torch

        obs_dim = rl_obs_dim(include_imu=False)
        hidden = int((amp_cfg or {}).get("disc_hidden_dim", 256))
        layers = int((amp_cfg or {}).get("disc_num_layers", 2))
        disc = AMPDiscriminator(state_dim=obs_dim, hidden_dim=hidden, num_layers=layers)
        try:
            state = torch.load(
                str(discriminator_path), map_location="cpu", weights_only=False
            )
        except TypeError:
            state = torch.load(str(discriminator_path), map_location="cpu")
        disc.load_state_dict(state)
        disc.eval()
        m = min(rollout.obs.shape[0], rollout.next_obs.shape[0], n)
        disc_summary = discriminator_realism_summary(
            disc, rollout.obs[:m], rollout.next_obs[:m]
        )

    metrics: dict[str, Any] = {
        "tracking_mean_mse": mean_mse,
        "tracking_per_joint_mse": per_joint_mse,
        "velocity_mse": vel_mse,
        "foot_sliding": foot_sliding,
    }
    if disc_summary is not None:
        metrics["discriminator"] = disc_summary

    return {
        "schema_version": EVAL_MOTION_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reference_sha256": reference_sha256,
        "checkpoint": checkpoint,
        "rollout_steps": int(rollout.motor_q.shape[0]),
        "metrics": metrics,
        "notes": (
            "foot_sliding uses ankle_velocity_energy proxy on rollout motor_q when T>=2; "
            "not a physics contact metric."
        ),
    }


def run_amp_eval(
    *,
    reference_path: Path,
    config: dict[str, Any],
    checkpoint_path: Path,
    output_path: Path,
    discriminator_path: Path | None = None,
    rollout_max_steps: int | None = None,
    seed: int = 42,
    deterministic: bool = True,
) -> dict[str, Any]:
    """Load AMP policy checkpoint, rollout, write eval_motion.json."""
    import torch
    from stable_baselines3 import PPO

    ref_raw = load_reference_trajectory_json(reference_path)
    err = validate_reference_trajectory_dict(ref_raw)
    if err:
        raise ValueError("Invalid reference_trajectory.json:\n" + "\n".join(err))

    env_cfg = g1_env_cfg_from_train_config(config)
    if env_cfg.include_imu_in_obs:
        raise ValueError("AMP eval supports env.include_imu_in_obs=false only")

    ref_motion = reference_motion_from_dict(ref_raw)
    env = G1TrackingEnv(ref_raw, env_cfg)

    model = PPO.load(str(checkpoint_path), env=env)

    eval_cfg = config.get("motion_eval") or {}
    max_steps = int(
        rollout_max_steps
        if rollout_max_steps is not None
        else eval_cfg.get("rollout_max_steps", 2048)
    )

    rollout = collect_rollout(model, env, max_steps=max_steps, seed=seed, deterministic=deterministic)

    disc_path = discriminator_path
    amp_cfg: dict[str, Any] | None = None
    if disc_path is None:
        cand = checkpoint_path.parent / "amp_discriminator.pt"
        if cand.is_file():
            disc_path = cand
    train_run_path = checkpoint_path.parent / "train_run.json"
    if train_run_path.is_file():
        tr = json.loads(train_run_path.read_text(encoding="utf-8"))
        amp_cfg = tr.get("amp") if isinstance(tr.get("amp"), dict) else None
        alt = tr.get("amp_discriminator_checkpoint")
        if isinstance(alt, str):
            ap = Path(alt)
            if ap.is_file():
                disc_path = ap

    report = build_eval_motion_report(
        reference_sha256=_sha256_file(reference_path),
        checkpoint=str(checkpoint_path.resolve()),
        joint_order=[str(x) for x in ref_raw["joint_order"]],
        rollout=rollout,
        ref=ref_motion,
        sim_dt=float(env_cfg.sim_dt),
        discriminator_path=disc_path,
        amp_cfg=amp_cfg,
    )

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
