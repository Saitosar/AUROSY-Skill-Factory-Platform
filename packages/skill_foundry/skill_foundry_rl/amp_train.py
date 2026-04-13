"""AMP training runner layered on top of PPO environment pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from skill_foundry_phase0.contract_validator import validate_reference_trajectory_dict
from skill_foundry_sim.reference_loader import load_reference_trajectory_json

from skill_foundry_rl.amp_discriminator import AMPDiscriminator
from skill_foundry_rl.g1_tracking_env import G1TrackingEnv, g1_env_cfg_from_train_config
from skill_foundry_rl.obs_schema import RL_OBS_SCHEMA_REF, rl_obs_dim
from skill_foundry_rl.product_validation import maybe_run_validation_after_train
from skill_foundry_rl.reference_motion import reference_motion_from_dict


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_policy_transitions(
    model: Any,
    env: G1TrackingEnv,
    *,
    n_steps: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    obs, _ = env.reset(seed=seed)
    cur: list[np.ndarray] = []
    nxt: list[np.ndarray] = []
    for _ in range(max(1, n_steps)):
        action, _ = model.predict(obs, deterministic=False)
        next_obs, _reward, terminated, truncated, _info = env.step(action)
        cur.append(np.asarray(obs, dtype=np.float32))
        nxt.append(np.asarray(next_obs, dtype=np.float32))
        if terminated or truncated:
            obs, _ = env.reset(seed=seed)
        else:
            obs = next_obs
    return np.stack(cur, axis=0), np.stack(nxt, axis=0)


def run_amp_train(
    *,
    reference_path: Path,
    config: dict[str, Any],
    output_dir: Path,
    demonstration_path: Path | None = None,  # Kept for API parity with other train runners.
) -> dict[str, Any]:
    """Train PPO policy and AMP discriminator with alternating updates."""
    import torch
    from stable_baselines3 import PPO

    if demonstration_path is not None:
        # Phase 4 AMP path currently uses reference trajectory only.
        _ = demonstration_path

    ref_raw = load_reference_trajectory_json(reference_path)
    err = validate_reference_trajectory_dict(ref_raw)
    if err:
        raise ValueError("Invalid reference_trajectory.json:\n" + "\n".join(err))

    env_cfg = g1_env_cfg_from_train_config(config)
    if env_cfg.include_imu_in_obs:
        raise ValueError("AMP mode currently supports env.include_imu_in_obs=false only")

    seed = int(config.get("seed", 42))
    ppo_cfg = config.get("ppo") or {}
    learning_rate = float(ppo_cfg.get("learning_rate", 3e-4))
    n_steps = int(ppo_cfg.get("n_steps", 2048))
    batch_size = int(ppo_cfg.get("batch_size", 256))
    n_epochs = int(ppo_cfg.get("n_epochs", 10))
    gamma = float(ppo_cfg.get("gamma", 0.99))
    total_timesteps = int(ppo_cfg.get("total_timesteps", 100_000))

    amp_cfg = config.get("amp") or {}
    disc_hidden_dim = int(amp_cfg.get("disc_hidden_dim", 256))
    disc_num_layers = int(amp_cfg.get("disc_num_layers", 2))
    disc_lr = float(amp_cfg.get("disc_learning_rate", 3e-4))
    disc_batch = int(amp_cfg.get("disc_batch_size", 256))
    disc_updates = int(amp_cfg.get("disc_updates_per_iter", 4))
    policy_chunk_steps = int(amp_cfg.get("policy_chunk_timesteps", max(1024, n_steps)))
    rollout_steps = int(amp_cfg.get("policy_rollout_steps", max(256, n_steps // 2)))

    torch.manual_seed(seed)
    np.random.seed(seed & 0xFFFFFFFF)
    rng = np.random.default_rng(seed)

    train_env = G1TrackingEnv(ref_raw, env_cfg)
    sample_env = G1TrackingEnv(ref_raw, env_cfg)
    reference_motion = reference_motion_from_dict(ref_raw)

    model = PPO(
        "MlpPolicy",
        train_env,
        learning_rate=learning_rate,
        n_steps=n_steps,
        batch_size=batch_size,
        n_epochs=n_epochs,
        gamma=gamma,
        verbose=0,
        seed=seed,
    )

    obs_dim = rl_obs_dim(include_imu=False)
    disc = AMPDiscriminator(
        state_dim=obs_dim,
        hidden_dim=disc_hidden_dim,
        num_layers=disc_num_layers,
    )
    disc_optim = torch.optim.Adam(disc.parameters(), lr=disc_lr)

    amp_metrics: list[dict[str, float]] = []
    iter_idx = 0
    while model.num_timesteps < total_timesteps:
        remain = total_timesteps - model.num_timesteps
        model.learn(total_timesteps=min(policy_chunk_steps, remain), reset_num_timesteps=False)

        pol_s_np, pol_n_np = _collect_policy_transitions(
            model,
            sample_env,
            n_steps=rollout_steps,
            seed=seed + iter_idx + 1,
        )
        exp_s_np, exp_n_np = reference_motion.sample_expert_states(rng, pol_s_np.shape[0])

        pol_s = torch.as_tensor(pol_s_np, dtype=torch.float32)
        pol_n = torch.as_tensor(pol_n_np, dtype=torch.float32)
        exp_s = torch.as_tensor(exp_s_np, dtype=torch.float32)
        exp_n = torch.as_tensor(exp_n_np, dtype=torch.float32)

        last_metrics: dict[str, float] = {}
        for _ in range(max(1, disc_updates)):
            idx_p = torch.randint(pol_s.shape[0], (min(disc_batch, pol_s.shape[0]),))
            idx_e = torch.randint(exp_s.shape[0], (min(disc_batch, exp_s.shape[0]),))
            loss, m = disc.loss(
                exp_s[idx_e],
                exp_n[idx_e],
                pol_s[idx_p],
                pol_n[idx_p],
            )
            disc_optim.zero_grad()
            loss.backward()
            disc_optim.step()
            last_metrics = m

        amp_reward_mean = float(disc.amp_reward(pol_s, pol_n).mean().item())
        amp_metrics.append(
            {
                "iter": float(iter_idx),
                "timesteps": float(model.num_timesteps),
                "amp_reward_mean": amp_reward_mean,
                "disc_total_loss": float(last_metrics.get("disc_total_loss", 0.0)),
                "disc_expert_score": float(last_metrics.get("disc_expert_score", 0.0)),
                "disc_policy_score": float(last_metrics.get("disc_policy_score", 0.0)),
            }
        )
        iter_idx += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    ckpt_stem = output_dir / "ppo_amp_G1TrackingEnv"
    model.save(str(ckpt_stem))
    ckpt_zip = Path(str(ckpt_stem) + ".zip")
    disc_path = output_dir / "amp_discriminator.pt"
    torch.save(disc.state_dict(), disc_path)

    mjcf_resolved = Path(str(env_cfg.mjcf_path)).expanduser().resolve()
    payload: dict[str, Any] = {
        "status": "ok",
        "phase": "4_amp",
        "obs_schema_ref": RL_OBS_SCHEMA_REF,
        "seed": seed,
        "reference_sha256": _sha256_file(reference_path),
        "mjcf_path": str(mjcf_resolved),
        "mjcf_sha256": _sha256_file(mjcf_resolved),
        "checkpoint": str(ckpt_zip),
        "amp_discriminator_checkpoint": str(disc_path),
        "total_timesteps_requested": total_timesteps,
        "total_timesteps_trained": int(model.num_timesteps),
        "amp": {
            "disc_hidden_dim": disc_hidden_dim,
            "disc_num_layers": disc_num_layers,
            "disc_updates_per_iter": disc_updates,
            "policy_chunk_timesteps": policy_chunk_steps,
            "policy_rollout_steps": rollout_steps,
            "metrics": amp_metrics,
        },
        "torch_version": torch.__version__,
    }

    run_json = output_dir / "train_run.json"
    run_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps({"amp_metrics": amp_metrics}, indent=2), encoding="utf-8")

    val_report = maybe_run_validation_after_train(
        output_dir=output_dir,
        checkpoint_path=ckpt_zip,
        reference_path=reference_path,
        train_config=config,
        seed=seed,
    )
    if val_report is not None:
        payload["product_validation"] = {
            "passed": bool(val_report.get("passed")),
            "report_path": str(output_dir / "validation_report.json"),
        }
    return payload
