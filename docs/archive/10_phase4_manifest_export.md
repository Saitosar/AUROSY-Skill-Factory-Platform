# Skill Foundry: Phase 4.1 — Manifest and export

This document specifies task **4.1** from [03_implementation_plan.md](03_implementation_plan.md): **export manifest**, **skill package archive**, and optional **ONNX** / **policy weights `.pt`**.

## Role in the pipeline

- **Phase 3 / 4.0** ([09_phase3_env_rewards.md](09_phase3_env_rewards.md), [../skill_foundry/14_video_to_motion_integration.md](../skill_foundry/14_video_to_motion_integration.md)): training writes `train_run.json` and checkpoint artifacts. PPO mode produces `ppo_G1TrackingEnv.zip`; AMP mode produces `ppo_amp_G1TrackingEnv.zip` and `amp_discriminator.pt`. `train_run.json` includes **MJCF provenance** (`mjcf_path`, `mjcf_sha256`, `env_snapshot`). **Phase 6.1** adds optional `validation_report.json`.
- **Phase 4.1 (this doc)**: Turn those artifacts into a **portable package** another developer can use for inference without the training codebase.

## Package layout (`.tar.gz`)

| Member | Description |
|--------|-------------|
| `manifest.json` | Contract: observations, action scaling, `dt`, PD gains, `joint_order`, `mjcf_sha256`, weights format |
| `reference_trajectory.json` | ReferenceTrajectory v1 (same file as training; SHA in `provenance.reference_sha256`) for Robot runtime inference |
| `ppo_G1TrackingEnv.zip` or `ppo_amp_G1TrackingEnv.zip` | SB3 PPO checkpoint (depends on training mode) |
| `amp_discriminator.pt` | Optional: AMP discriminator checkpoint from `--mode amp` runs |
| `policy_weights.pt` | Optional: `policy_state_dict` from the SB3 policy |
| `policy.onnx` | Optional: ONNX graph mapping `obs` → `action_mean` (Gaussian mean before sampling) |
| `validation_report.json` | Optional (Phase 6.1): product validation report; mirrored in `manifest.json` → `product_validation` |
| `eval_motion.json` | Optional (Phase 5): AMP motion quality report; mirrored in `manifest.json` → `motion.eval_report` |

## Manifest contract

- JSON Schema: [contracts/export/export_manifest.schema.json](contracts/export/export_manifest.schema.json)
- Example: [contracts/examples/export/export_manifest.valid.json](contracts/examples/export/export_manifest.valid.json)

Key fields:

- **`package_version`**: semver of the **export format** (not the RL code version).
- **`manifest_schema_ref`**: `skill_foundry_export_manifest_v1`
- **`observation`**: `obs_schema_ref` (`skill_foundry_rl_tracking_v1`), `vector_dim`, ordered **`blocks`** (name, offset, length)
- **`action`**: Box `[-1, 1]` and **`residual_scale_rad`** (= `env.delta_max`)
- **`control`**: `dt_s` (= `env.sim_dt`), `kp`, `kd`
- **`robot`**: `profile` (e.g. `unitree_g1_29dof`), `mjcf_sha256`, optional `mjcf_path` as trained
- **`joint_order`**: from ReferenceTrajectory v1 (must match training reference)
- **`reference_trajectory`**: bundled file name (`reference_trajectory.json`) and optional `schema_ref` for runtime loaders
- **`weights`**: `format: stable_baselines3_ppo_zip`, `filename`, **`sha256`** (SHA-256 файла чекпоинта; записывается при `pack`, проверяется в `skill-foundry-runtime` — см. [13_phase6_runtime_security.md](13_phase6_runtime_security.md))
- **`motion`** (optional, Phase 5 / video-to-motion): when present, documents retargeting context and AMP extras:
  - `reference_motion_source`: bundled reference filename (typically `reference_trajectory.json`)
  - `retarget_profile`: `robot`, `source_skeleton`, `joint_map_version` (defaults: `mediapipe_pose_33`, `1.0`)
  - `eval_report`: `{ filename: eval_motion.json, sha256, schema_version? }` when that file was packed from `run_dir`
  - `amp`: training-phase hints (`train_phase`, `policy_weights_filename`, discriminator dims, optional `discriminator_bundle_filename: amp_discriminator.pt` when packed)
- **`provenance`**: `reference_sha256`, optional `train_config_sha256`, `phase`, `torch_version`
- **`product_validation`**: optional summary when `validation_report.json` was packed (Phase 6.1)

## CLI

Install (same repo as RL worker):

```bash
cd /path/to/AUROSY_creators_factory_platform
pip install -e "./unitree_sdk2_python"
pip install -e "./packages/skill_foundry[rl,export]"
```

Create a package:

```bash
skill-foundry-package pack \
  --train-config /path/to/ppo_train_config.json \
  --reference-trajectory /path/to/reference_trajectory.json \
  --run-dir /path/to/ppo_run_out \
  --output /path/to/skill_bundle.tar.gz
```

Options:

- `--policy-pt` — include `policy_weights.pt`
- `--onnx` — export `policy.onnx` (requires `onnx` from the `export` extra)
- `--package-version`, `--robot-profile`, `--onnx-opset`
- **Phase 5:** `--include-amp-discriminator` — copy `amp_discriminator.pt` from `run_dir` when present; `--record-motion-metadata` — always emit `manifest.motion` with retarget defaults; `--joint-map-version`, `--motion-source-skeleton` — override retarget profile strings

If `run_dir` contains `eval_motion.json`, it is packed automatically and `manifest.motion.eval_report` is populated. Older bundles without `motion` remain valid.

The **reference file** must match training: its SHA-256 must equal `train_run.json` → `reference_sha256`. The **MJCF** on disk must match `train_run.json` → `mjcf_sha256` when present.

## Verifying MJCF identity

Recompute SHA-256 of the MJCF file you will use on the robot and compare to `manifest.json` → `robot.mjcf_sha256`. A mismatch means observations/dynamics may not match training.

## Inference notes

- Loading the **SB3 zip** in Python: `stable_baselines3.PPO.load(...)` — observation vector must match `manifest.observation` (same layout as `G1TrackingEnv`).
- **ONNX** export traces the **mean action** head (see `skill_foundry_export/onnx_export.py`); stochastic sampling is not in the ONNX graph.
- Phase **4.2** ([03_implementation_plan.md](03_implementation_plan.md)) consumes this package in **Robot runtime** (`skill_foundry_runtime`): `pip install -e "./packages/skill_foundry[runtime]"` (и `-e "./unitree_sdk2_python"`) затем `skill-foundry-runtime run --package ... --mjcf ...` (`--mode mujoco` or `--mode dds`). The archive includes `reference_trajectory.json`; override with `--reference` only if the file matches `provenance.reference_sha256`.

## Related code

- `packages/skill_foundry/skill_foundry_export/` — manifest builder, `package_skill`, ONNX helper, CLI
- `packages/skill_foundry/skill_foundry_rl/obs_schema.py` — must stay aligned with `manifest.observation`
- `packages/skill_foundry/skill_foundry_rl/ppo_train.py` — writes extended `train_run.json` for export

## Definition of done (task 4.1)

A third party can unpack `skill_bundle.tar.gz`, read `manifest.json`, and understand how to build an inference pipeline (Python/SB3 and/or ONNX) without access to the original training source tree, except for secrets and site-specific calibration.
