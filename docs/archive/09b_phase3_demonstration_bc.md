# Skill Foundry: Phase 3.3 — Demonstration initialization (behavior cloning)

This document specifies task **3.3** from [03_implementation_plan.md](03_implementation_plan.md): **offline behavior cloning** on `DemonstrationDataset` v1 before PPO, with the same action space as [09_phase3_env_rewards.md](09_phase3_env_rewards.md) (normalized residual \(\Delta \in [-1,1]^{29}\)).

## Role in the pipeline

- **Phase 2** ([07_phase2_trajectory_recorder.md](07_phase2_trajectory_recorder.md)) produces `demonstration_dataset.json` from headless playback.
- **Phase 3.2** trains PPO on `G1TrackingEnv` without demos by default.
- **Phase 3.3 (this doc)** optionally **pretrains the policy mean** on offline tuples \((s,a)\) built from the demo + the **same** `reference_trajectory.json` used for training.

## Observation alignment

Demonstrations use `obs_schema_ref` = `skill_foundry_sim_motor_q_dq_ctrl_v1` (58-D: `motor_q`, `motor_dq`). The RL policy expects `skill_foundry_rl_tracking_v1` (87-D without IMU). The module `skill_foundry_rl.demo_rl_align` maps each demo step to RL observations by interpolating the reference at the correct simulation time and forming the tracking-error block (same semantics as `G1TrackingEnv`).

**Time index:** a demo step `k` (0-based) corresponds to simulation time \((k+1)/\text{sampling\_hz}\) after the corresponding `mj_step` in playback (see [headless_playback.py](../../packages/skill_foundry/skill_foundry_sim/headless_playback.py)).

**IMU:** BC pretrain is supported only when `env.include_imu_in_obs` is **false** (demonstrations do not contain an IMU block).

## Action labels (MVP)

The expert residual applied on top of the reference is **unknown** from torque-only logs. For recordings from **reference-only playback** (no RL policy on the robot), the natural residual target is **zero** (follow the reference). Behavior cloning therefore uses **\(a^\* = 0 \in \mathbb{R}^{29}\)** in normalized action space.

**Implication:** the learning signal is weak unless you later add demonstrations with non-trivial residuals (e.g. student rollouts). Measure **sample efficiency** with an A/B protocol (below); do not treat “runs without error” as product success alone.

## Configuration

In the PPO train JSON (see [golden/v1/ppo_train_config.example.json](golden/v1/ppo_train_config.example.json)):

| Key | Meaning |
|-----|---------|
| `bc.enabled` | If true, run BC before `PPO.learn`. |
| `bc.demonstration_dataset` | Path to `demonstration_dataset.json`. |
| `bc.epochs` | Offline epochs over the dataset (default 20). |
| `bc.batch_size` | Minibatch size (default 256). |
| `bc.learning_rate` | Adam LR for BC (default 0.001). |

CLI: `skill-foundry-train --mode train ... --demonstration-dataset PATH` **overrides** `bc.demonstration_dataset` when both are set.

## CLI example

```bash
cd /path/to/AUROSY_creators_factory_platform
pip install -e "./unitree_sdk2_python"
pip install -e "./packages/skill_foundry[rl]"
skill-foundry-train \
  --mode train \
  --config /path/to/ppo_train_config.json \
  --reference-trajectory /path/to/reference_trajectory.json \
  --demonstration-dataset /path/to/demonstration_dataset.json
```

Enable BC in the JSON with `"bc": { "enabled": true, ... }`. The demonstration **must** have been recorded against the **same** reference trajectory file you pass to `--reference-trajectory`.

## Artifacts

`train_run.json` includes `phase`: `3.3_ppo_bc` when BC ran, plus a `bc` object (`bc_final_loss`, `num_steps`, `demonstration_sha256`, etc.).

## A/B protocol (definition of done)

1. Fix a **reference** and **validation seed** (as in Phase 3.2 tests).
2. Train **baseline** PPO with `bc.enabled` false for `total_timesteps` \(T\).
3. Train **with BC** with the same \(T\) and seeds, same hyperparameters except BC block.
4. Compare **time to threshold**: e.g. first timestep where moving-average eval reward (or tracking MSE) crosses a bar documented for your product, or total reward at \(T\).

Record results in your experiment log; thresholds are product-specific, not fixed wall-clock SLA.

## Mixed BC + PPO loss (future)

An auxiliary BC term inside PPO updates is **not** part of this MVP. Add it only after offline pretrain shows insufficient gain, to avoid extra tuning surface.

## Related code

- [demo_rl_align.py](../../packages/skill_foundry/skill_foundry_rl/demo_rl_align.py) — alignment and dataset stacking.
- [bc_pretrain.py](../../packages/skill_foundry/skill_foundry_rl/bc_pretrain.py) — MSE on policy mean.
- [ppo_train.py](../../packages/skill_foundry/skill_foundry_rl/ppo_train.py) — `run_ppo_train(..., demonstration_path=...)`.

## Related documents

- [04_phase0_contracts.md](04_phase0_contracts.md) — RL vs demo schemas.
- [09_phase3_env_rewards.md](09_phase3_env_rewards.md) — environment and PPO baseline.
