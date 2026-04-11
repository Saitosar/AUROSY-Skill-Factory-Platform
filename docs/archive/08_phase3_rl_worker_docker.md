# Skill Foundry: Phase 3 — RL worker Docker image (task 3.1)

This document specifies task **3.1** from [03_implementation_plan.md](03_implementation_plan.md): a **Docker image** with pinned **CUDA / PyTorch / Python** stack and a single **entrypoint** that accepts a training config plus paths to **ReferenceTrajectory v1** and, optionally, **DemonstrationDataset v1** (see [04_phase0_contracts.md](04_phase0_contracts.md) §2).

## Role in the pipeline

Matches [02_architecture.md](02_architecture.md) §6: **Training orchestrator → RL worker** (local or remote). The MVP worker runs a **deterministic smoke train** (contract validation + tiny PyTorch loop on CPU for reproducible metrics). Full MuJoCo RL (observations, rewards, PPO, etc.) is **task 3.2**, documented in [09_phase3_env_rewards.md](09_phase3_env_rewards.md).

## Smoke (3.1) vs train (3.2)

| Mode | CLI | Needs MJCF | Behavior |
|------|-----|------------|----------|
| **smoke** (default) | `--mode smoke` or omit | No | Validates JSON + tiny CPU torch loop ([smoke_train.py](../../packages/skill_foundry/skill_foundry_rl/smoke_train.py)) |
| **train** | `--mode train` | **Yes** — set `env.mjcf_path` in config to mounted `scene_29dof.xml` | PPO on `G1TrackingEnv` ([ppo_train.py](../../packages/skill_foundry/skill_foundry_rl/ppo_train.py)) |

Use [golden/v1/ppo_train_config.example.json](golden/v1/ppo_train_config.example.json) as a template for Phase 3.2. Mount `unitree_mujoco/` read-only if the image does not embed those assets.

## Image contents

- **Base:** `pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime` (see comments in [docker/skill_foundry_rl/Dockerfile](../../docker/skill_foundry_rl/Dockerfile); pin updated when upgrading).
- **Python packages:** `pip install -e "/opt/skill_foundry/unitree_sdk2_python[rl]"` then `pip install -e "/opt/skill_foundry/packages/skill_foundry[rl]"` — upstream `unitree_sdk2py` plus AUROSY modules (`skill_foundry_phase0`, `skill_foundry_sim`, `skill_foundry_rl`, …).
- **Environment:** `MUJOCO_GL=egl` for headless-friendly OpenGL where applicable.

## Host requirements

- [Docker](https://docs.docker.com/get-docker/) with BuildKit (default in recent versions).
- **GPU training:** [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) so `docker run --gpus all` works. The Phase 3.1 **smoke** loop runs on **CPU** for stable floating-point logs; the image still includes CUDA-enabled PyTorch for later phases.

## Build

From the **repository root** (context must include `unitree_sdk2_python/` and `packages/skill_foundry/`):

```bash
docker build -f docker/skill_foundry_rl/Dockerfile -t skill-foundry-rl:3.1 .
```

A [`.dockerignore`](../../.dockerignore) at the repo root excludes heavy paths not needed for this image (e.g. `docs/`, `unitree_mujoco/`).

## Entrypoint / CLI

Container `ENTRYPOINT` is `skill-foundry-train` (see `packages/skill_foundry/skill_foundry_rl/cli.py`).

| Argument | Required | Description |
|----------|----------|-------------|
| `--config` | yes | JSON or YAML file: `seed`, `smoke_steps`, `learning_rate`, `output_dir`, … |
| `--reference-trajectory` | yes | Path to `reference_trajectory.json` (ReferenceTrajectory v1). |
| `--demonstration-dataset` | no | Path to `demonstration_dataset.json` (DemonstrationDataset v1). |

`output_dir` in the config may be relative to the config file’s directory (same rule as the local CLI).

**Local install (without Docker):** from the repo root, `pip install -e "./unitree_sdk2_python"` then `pip install -e "./packages/skill_foundry[rl]"`, then `python -m skill_foundry_rl` with the same arguments.

## Run (example with golden data)

Golden fixtures: [golden/v1](golden/v1/).

1. Prepare a config that writes under a mounted output directory, e.g. `smoke_train_config.docker.json`:

```json
{
  "seed": 42,
  "smoke_steps": 5,
  "learning_rate": 0.01,
  "output_dir": "/out/smoke_run"
}
```

2. Run:

```bash
docker run --rm \
  -v "$(pwd)/docs/skill_foundry/golden/v1:/data:ro" \
  -v "$(pwd)/runs:/out" \
  skill-foundry-rl:3.1 \
  --config /data/smoke_train_config.docker.json \
  --reference-trajectory /data/reference_trajectory.json
```

Optional: add `--demonstration-dataset /data/demonstration_dataset.json` if present.

3. **GPU passthrough** (optional for this smoke; useful for future RL):

```bash
docker run --rm --gpus all \
  -v "$(pwd)/docs/skill_foundry/golden/v1:/data:ro" \
  -v "$(pwd)/runs:/out" \
  skill-foundry-rl:3.1 \
  --config /data/smoke_train_config.docker.json \
  --reference-trajectory /data/reference_trajectory.json
```

**Artifacts:** `train_run.json` and `smoke_checkpoint.pt` under `output_dir` (e.g. `./runs/smoke_run` on the host when `/out` is mounted).

## Definition of done (task 3.1)

- Image builds from the Dockerfile.
- One documented command reproduces a **successful** smoke run on golden `reference_trajectory.json` (and optional demo), producing `train_run.json` with `status: ok` and reproducible `losses` for the same seed (CPU smoke).

## Risks and licensing

- **Image size:** PyTorch + CUDA layers are large; use `.dockerignore` and pinned tags.
- **Licenses:** NVIDIA CUDA/cuDNN and MuJoCo are subject to their respective terms; use images and wheels in compliance with your deployment.

## Related code

- Image: [docker/skill_foundry_rl/Dockerfile](../../docker/skill_foundry_rl/Dockerfile), [docker/skill_foundry_rl/README.md](../../docker/skill_foundry_rl/README.md).
- Python: `packages/skill_foundry/skill_foundry_rl/`.

## Related documents

- [09_phase3_env_rewards.md](09_phase3_env_rewards.md) — Phase 3.2 environment, rewards, `train` mode.
