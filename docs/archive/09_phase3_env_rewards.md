# Skill Foundry: Phase 3 — Environment and rewards (task 3.2)

This document specifies task **3.2** from [03_implementation_plan.md](03_implementation_plan.md): the **G1 MuJoCo tracking environment**, **observation schema** for training (aligned with future export manifest, Phase 4), **reward terms**, **early stopping**, and CLI/Docker usage alongside Phase 3.1 smoke train.

## Role in the pipeline

- **Phase 3.1** ([08_phase3_rl_worker_docker.md](08_phase3_rl_worker_docker.md)): Docker image + `skill-foundry-train` in **`smoke`** mode — contract validation + tiny CPU torch loop (no MuJoCo RL).
- **Phase 3.2 (this doc)**: **`train`** mode — **PPO** on `G1TrackingEnv` using the same **ReferenceTrajectory v1** and the same **PD law** as [06_phase2_sim_playback.md](06_phase2_sim_playback.md) / `skill_foundry_sim` headless playback, with a **residual** on joint targets from the policy.

## Observation schema (`RL_OBS_SCHEMA_REF`)

Constant in code: `skill_foundry_rl.obs_schema.RL_OBS_SCHEMA_REF` = **`skill_foundry_rl_tracking_v1`**.

| Block | Size | Contents |
|-------|------|----------|
| Motor positions | 29 | `motor_q` (same index order as `JointController` / playback) |
| Motor velocities | 29 | `motor_dq` |
| Tracking error | 29 | `q_meas - q_ref(t)` per motor; motors not listed in reference `joint_order` track current angle so error is 0 |
| IMU (optional) | 13 | If `env.include_imu_in_obs: true`: concat `imu_quat` (4), `imu_gyro` (3), `imu_acc` (3) from MJCF sensors |

Default vector size: **87** (no IMU). With IMU: **100**.

**DemonstrationDataset** uses a different schema (`skill_foundry_sim_motor_q_dq_ctrl_v1` — 58-D); see [04_phase0_contracts.md](04_phase0_contracts.md) §RL vs demo.

## Action

- Box **[-1, 1]**^{29}, scaled by `env.delta_max` (radians) to a **residual** Δ added to reference motor targets:
  - `q_des = q_ref(t) + Δ`, then `ctrl = kp*(q_des - q) + kd*(dq_ref - dq)` (same as dynamic playback).

## Rewards (scalar per step)

Weights from `env.reward_weights` (defaults shown):

| Term | Default weight key | Formula (conceptually) |
|------|---------------------|-------------------------|
| Tracking | `w_track` | `-w_track * mean((q - q_ref)^2)` at time after step |
| Survival | `w_alive` | `+w_alive` while upright; 0 if fallen |
| Energy | `w_energy` | `-w_energy * sum(ctrl^2)` |
| Jerk | `w_jerk` | `-w_jerk * sum((ctrl_t - ctrl_{t-1})^2)` |

**Fall:** episode terminates if pelvis height `qpos[2]` &lt; `env.min_base_height`.

**Truncation:** when simulation time passes the end of the reference (`t > t_max` from the trajectory) or `env.max_episode_steps` is reached.

## Training stop (not wall-clock SLA)

Configured under `early_stop` and `ppo`:

- `ppo.total_timesteps` — hard cap on environment steps.
- Optional **plateau**: `early_stop.eval_freq`, `early_stop.plateau_patience`, `early_stop.plateau_min_delta`, `early_stop.val_seed`. Set `plateau_patience: 0` to disable.

Artifacts: `train_run.json` (includes `mjcf_path`, `mjcf_sha256`, `env_snapshot` for Phase 4 export), `metrics.json`, `ppo_G1TrackingEnv.zip` (Stable-Baselines3 checkpoint). See [10_phase4_manifest_export.md](10_phase4_manifest_export.md).

## CLI

```bash
cd unitree_sdk2_python
pip install -e ".[rl]"
skill-foundry-train \
  --mode train \
  --config /path/to/ppo_train_config.json \
  --reference-trajectory /path/to/reference_trajectory.json
```

`--mode` defaults to `smoke`. You can set `"mode": "train"` inside the JSON instead.

## Config example

See [golden/v1/ppo_train_config.example.json](golden/v1/ppo_train_config.example.json).

## Docker / MJCF

The RL worker image installs Python deps including **Gymnasium** and **Stable-Baselines3**. **MJCF** files are not copied into the minimal image by default (see [.dockerignore](../../.dockerignore)); mount the host `unitree_mujoco` tree or pass `env.mjcf_path` inside the container to a mounted XML (e.g. `scene_29dof.xml`). Phase 3.1 smoke **does not** require MJCF; Phase 3.2 **does**.

## Related code

- `unitree_sdk2_python/skill_foundry_rl/g1_tracking_env.py` — `G1TrackingEnv`, `G1TrackingEnvConfig`
- `unitree_sdk2_python/skill_foundry_rl/ppo_train.py` — `run_ppo_train`; optional post-train **`validation_report.json`** (Phase 6.1 — [12_phase6_product_validation.md](12_phase6_product_validation.md))
- `unitree_sdk2_python/skill_foundry_rl/obs_schema.py` — `RL_OBS_SCHEMA_REF`, `rl_obs_dim`
- `unitree_sdk2_python/skill_foundry_export/` — Phase 4.1 packaging (`skill-foundry-package`); spec: [10_phase4_manifest_export.md](10_phase4_manifest_export.md)

## Related documents

- [04_phase0_contracts.md](04_phase0_contracts.md) — training contract; RL vs demo `obs_schema_ref`
- [08_phase3_rl_worker_docker.md](08_phase3_rl_worker_docker.md) — Docker image and smoke mode
- [06_phase2_sim_playback.md](06_phase2_sim_playback.md) — shared PD / reference interpolation
- [12_phase6_product_validation.md](12_phase6_product_validation.md) — product thresholds and report after training

## Definition of done (task 3.2)

Training on a fixed **golden** reference meets product thresholds on a **validation seed** (tracking error, fall rate); see tests under `skill_foundry_rl/tests/` and thresholds noted in test docstrings / config.
