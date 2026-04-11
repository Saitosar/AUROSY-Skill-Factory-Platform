# Skill Foundry RL worker image (Phase 3.1 smoke + Phase 3.2 PPO)

Build from the **repository root** (so `unitree_sdk2_python/` is in context):

```bash
docker build -f docker/skill_foundry_rl/Dockerfile -t skill-foundry-rl:3.1 .
```

## Smoke train (Phase 3.1)

Run with mounted golden data (see [08_phase3_rl_worker_docker.md](../../docs/skill_foundry/08_phase3_rl_worker_docker.md)):

```bash
docker run --rm --gpus all \
  -v "$(pwd)/docs/skill_foundry/golden/v1:/data:ro" \
  -v "$(pwd)/runs:/out" \
  skill-foundry-rl:3.1 \
  --config /data/smoke_train_config.docker.json \
  --reference-trajectory /data/reference_trajectory.json
```

Use `smoke_train_config.docker.json` so `output_dir` is `/out/smoke_run` under the `/out` volume.

## PPO train (Phase 3.2)

Mount a **MuJoCo scene** (e.g. repo `unitree_mujoco/`) and pass `env.mjcf_path` inside the config. Example:

```bash
docker run --rm --gpus all \
  -v "$(pwd)/docs/skill_foundry/golden/v1:/data:ro" \
  -v "$(pwd)/unitree_mujoco:/mujoco:ro" \
  -v "$(pwd)/runs:/out" \
  skill-foundry-rl:3.1 \
  --mode train \
  --config /data/ppo_train_config.docker.json \
  --reference-trajectory /data/reference_trajectory.json
```

Copy [ppo_train_config.example.json](../../docs/skill_foundry/golden/v1/ppo_train_config.example.json) to `ppo_train_config.docker.json`, set `output_dir` to `/out/ppo_run`, and set `env.mjcf_path` to `/mujoco/unitree_robots/g1/scene_29dof.xml` when using the mount above. Full spec: [09_phase3_env_rewards.md](../../docs/skill_foundry/09_phase3_env_rewards.md).

## Optional: BC pretrain (Phase 3.3)

If you have a `demonstration_dataset.json` recorded against the same reference (see [07_phase2_trajectory_recorder.md](../../docs/skill_foundry/07_phase2_trajectory_recorder.md)), mount it and pass `--demonstration-dataset`, and set `"bc": { "enabled": true, ... }` in your train config. Spec: [09b_phase3_demonstration_bc.md](../../docs/skill_foundry/09b_phase3_demonstration_bc.md).

## Export package (Phase 4.1)

After training, build a portable skill bundle (`manifest.json` + checkpoint archive) on the host where `unitree_sdk2_python` is installed with export extras:

```bash
cd unitree_sdk2_python && pip install -e ".[rl,export]"
skill-foundry-package pack \
  --train-config /path/to/ppo_train_config.json \
  --reference-trajectory /path/to/reference_trajectory.json \
  --run-dir /path/to/ppo_run_out \
  --output ./skill_bundle.tar.gz
```

See [10_phase4_manifest_export.md](../../docs/skill_foundry/10_phase4_manifest_export.md).
