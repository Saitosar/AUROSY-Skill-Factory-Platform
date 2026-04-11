"""PPO training on G1TrackingEnv (Phase 3.2): plateau early stop, metrics, checkpoint."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from skill_foundry_phase0.contract_validator import validate_reference_trajectory_dict
from skill_foundry_sim.reference_loader import load_reference_trajectory_json

from skill_foundry_rl.bc_pretrain import run_bc_pretrain
from skill_foundry_rl.demo_rl_align import build_bc_dataset_arrays, load_demonstration_dataset
from skill_foundry_rl.g1_tracking_env import G1TrackingEnv, g1_env_cfg_from_train_config
from skill_foundry_rl.product_validation import maybe_run_validation_after_train
from skill_foundry_rl.obs_schema import RL_OBS_SCHEMA_REF


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_ppo_train(
    *,
    reference_path: Path,
    config: dict[str, Any],
    output_dir: Path,
    demonstration_path: Path | None = None,
) -> dict[str, Any]:
    """Train PPO on :class:`G1TrackingEnv`; write ``train_run.json`` and model zip under ``output_dir``.

    Optional Phase 3.3: when ``bc.enabled`` and a demonstration JSON path is set, run offline BC
    on the policy mean before ``learn``. CLI ``--demonstration-dataset`` overrides ``bc.demonstration_dataset``.
    """
    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.evaluation import evaluate_policy

    ref_raw = load_reference_trajectory_json(reference_path)
    err = validate_reference_trajectory_dict(ref_raw)
    if err:
        raise ValueError("Invalid reference_trajectory.json:\n" + "\n".join(err))

    seed = int(config.get("seed", 42))
    env_cfg_dict = config.get("env") or {}
    mjcf_path = env_cfg_dict.get("mjcf_path") or config.get("mjcf_path")
    if not mjcf_path:
        raise ValueError("train config must set env.mjcf_path (path to G1 MJCF, e.g. scene_29dof.xml)")

    env_cfg = g1_env_cfg_from_train_config(config)

    ppo_cfg = config.get("ppo") or {}
    learning_rate = float(ppo_cfg.get("learning_rate", 3e-4))
    n_steps = int(ppo_cfg.get("n_steps", 2048))
    batch_size = int(ppo_cfg.get("batch_size", 256))
    n_epochs = int(ppo_cfg.get("n_epochs", 10))
    gamma = float(ppo_cfg.get("gamma", 0.99))
    total_timesteps = int(ppo_cfg.get("total_timesteps", 100_000))

    early = config.get("early_stop") or {}
    eval_freq = int(early.get("eval_freq", 4096))
    val_seed = int(early.get("val_seed", seed + 1))
    plateau_patience = int(early.get("plateau_patience", 0))
    plateau_min_delta = float(early.get("plateau_min_delta", 0.01))

    torch.manual_seed(seed)
    np.random.seed(seed & 0xFFFFFFFF)

    train_env = G1TrackingEnv(ref_raw, env_cfg)
    eval_env = G1TrackingEnv(ref_raw, env_cfg)

    class PlateauEvalCallback(BaseCallback):
        def __init__(self) -> None:
            super().__init__(0)
            self.best_mean_reward = -np.inf
            self.no_improve_count = 0
            self.eval_history: list[float] = []

        def _on_step(self) -> bool:
            if plateau_patience <= 0 or eval_freq <= 0:
                return True
            if self.n_calls % eval_freq != 0:
                return True
            eval_env.reset(seed=val_seed)
            mean_reward, _ = evaluate_policy(
                self.model,
                eval_env,
                n_eval_episodes=1,
                deterministic=True,
            )
            mr = float(mean_reward)
            self.eval_history.append(mr)
            if mr > self.best_mean_reward + plateau_min_delta:
                self.best_mean_reward = mr
                self.no_improve_count = 0
            else:
                self.no_improve_count += 1
            if self.no_improve_count >= plateau_patience:
                return False
            return True

    plateau_cb = PlateauEvalCallback()

    bc_cfg = config.get("bc") or {}
    bc_enabled = bool(bc_cfg.get("enabled", False))
    bc_demo_cfg = bc_cfg.get("demonstration_dataset")
    demo_resolved: Path | None = demonstration_path
    if demo_resolved is None and isinstance(bc_demo_cfg, str) and bc_demo_cfg.strip():
        demo_resolved = Path(bc_demo_cfg).expanduser()
    bc_info: dict[str, Any] | None = None

    if bc_enabled:
        if env_cfg.include_imu_in_obs:
            raise ValueError(
                "bc.enabled requires env.include_imu_in_obs false (demonstrations have no IMU block)"
            )
        if demo_resolved is None or not demo_resolved.is_file():
            raise ValueError(
                "bc.enabled requires a demonstration JSON path "
                "(--demonstration-dataset or bc.demonstration_dataset in config)"
            )
        demo_raw = load_demonstration_dataset(demo_resolved)
        obs_bc, act_bc, ds_meta = build_bc_dataset_arrays(
            demo_raw,
            ref_raw,
            include_imu=False,
        )
        bc_epochs = int(bc_cfg.get("epochs", 20))
        bc_batch = int(bc_cfg.get("batch_size", 256))
        bc_lr = float(bc_cfg.get("learning_rate", 1e-3))

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

    if bc_enabled:
        bc_info = run_bc_pretrain(
            model,
            obs_bc,
            act_bc,
            epochs=bc_epochs,
            batch_size=bc_batch,
            learning_rate=bc_lr,
        )
        bc_info = {**bc_info, **ds_meta, "demonstration_sha256": _sha256_file(demo_resolved)}

    model.learn(total_timesteps=total_timesteps, callback=plateau_cb)

    output_dir.mkdir(parents=True, exist_ok=True)
    ckpt_stem = output_dir / "ppo_G1TrackingEnv"
    model.save(str(ckpt_stem))
    ckpt_zip = Path(str(ckpt_stem) + ".zip")

    mjcf_resolved = Path(str(mjcf_path)).expanduser().resolve()
    mjcf_sha256 = _sha256_file(mjcf_resolved)
    env_snapshot: dict[str, Any] = {
        "mjcf_path": str(mjcf_resolved),
        "sim_dt": env_cfg.sim_dt,
        "kp": env_cfg.kp,
        "kd": env_cfg.kd,
        "delta_max": env_cfg.delta_max,
        "min_base_height": env_cfg.min_base_height,
        "max_episode_steps": env_cfg.max_episode_steps,
        "include_imu_in_obs": env_cfg.include_imu_in_obs,
        "reward_weights": env_cfg.reward_weights or {},
    }

    phase = "3.3_ppo_bc" if bc_enabled else "3.2_ppo"
    payload: dict[str, Any] = {
        "status": "ok",
        "phase": phase,
        "obs_schema_ref": RL_OBS_SCHEMA_REF,
        "seed": seed,
        "reference_sha256": _sha256_file(reference_path),
        "mjcf_path": str(mjcf_resolved),
        "mjcf_sha256": mjcf_sha256,
        "env_snapshot": env_snapshot,
        "checkpoint": str(ckpt_zip),
        "total_timesteps_requested": total_timesteps,
        "total_timesteps_trained": int(model.num_timesteps),
        "plateau_stopped": bool(
            plateau_patience > 0 and plateau_cb.no_improve_count >= plateau_patience
        ),
        "eval_mean_rewards": plateau_cb.eval_history,
        "torch_version": torch.__version__,
    }
    if bc_info is not None:
        payload["bc"] = bc_info
    run_json = output_dir / "train_run.json"
    run_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "eval_mean_rewards": plateau_cb.eval_history,
                "best_eval_reward": plateau_cb.best_mean_reward,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

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
