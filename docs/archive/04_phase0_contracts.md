# Skill Foundry: Phase 0 contracts

This document implements Phase 0 from `03_implementation_plan.md`.

## 1) Authoring contract v1

Required files:

- `keyframes.json`
- `motion.json`
- `scenario.json`

Rules:

- `schema_version` is required and equals `1.0.0`.
- Authoring angles use `degrees`.
- Authoring time uses `seconds`.
- Joint ids are numeric strings (`"0"`..`"28"` for current G1 profile).
- Keyframe timestamps are strictly increasing.

## 2) Training contract v1

Required files:

- `reference_trajectory.json`
- `demonstration_dataset.json`

Rules:

- `ReferenceTrajectory` uses `radians`, `seconds`, and fixed `frequency_hz`.
- `joint_order` is mandatory and defines index-to-joint mapping for all arrays.
- `joint_positions` shape is `[T, D]`, where `D == len(joint_order)`.
- Optional `joint_velocities` must match `[T, D]`.
- MVP root/base model is fixed to `root_not_in_reference`.
- `DemonstrationDataset` stores episodes with per-step `obs`, `act`, `done`.
- `obs_schema_ref` must be present to align with future inference manifest.

**RL training vs DemonstrationDataset:** offline demos produced by SimPlayback use `obs_schema_ref` = `skill_foundry_sim_motor_q_dq_ctrl_v1` (motor positions + velocities only; see `skill_foundry_sim/demonstration_dataset.py`). Phase 3.2 RL uses a separate training observation layout identified by `skill_foundry_rl_tracking_v1` (adds reference tracking error and optional IMU); see [09_phase3_env_rewards.md](09_phase3_env_rewards.md). Export manifest (Phase 4) must reference the schema actually used at inference (typically the RL/inference schema, not the raw demo schema, unless they are explicitly aligned).

## 3) Canonical joint order (G1 29DoF profile)

Source: `unitree_sdk2_python/core_control/joint_controller.py` (`JointController.JOINT_MAP`).

- 0: left_hip_pitch
- 1: left_hip_roll
- 2: left_hip_yaw
- 3: left_knee
- 4: left_ankle_pitch
- 5: left_ankle_roll
- 6: right_hip_pitch
- 7: right_hip_roll
- 8: right_hip_yaw
- 9: right_knee
- 10: right_ankle_pitch
- 11: right_ankle_roll
- 12: waist_yaw
- 13: waist_roll
- 14: waist_pitch
- 15: left_shoulder_pitch
- 16: left_shoulder_roll
- 17: left_shoulder_yaw
- 18: left_elbow
- 19: left_wrist_roll
- 20: left_wrist_pitch
- 21: left_wrist_yaw
- 22: right_shoulder_pitch
- 23: right_shoulder_roll
- 24: right_shoulder_yaw
- 25: right_elbow
- 26: right_wrist_roll
- 27: right_wrist_pitch
- 28: right_wrist_yaw

## 4) Compatibility note with existing repository data

Current motion packs in `unitree_sdk2_python/mid_level_motions/**/pose.json` are legacy pose-only arrays and do not contain:

- `schema_version`
- units metadata
- keyframe timestamps
- scenario-level transition metadata

For Phase 0, they are treated as source material. Migration/adaptation path:

1. Wrap legacy pose arrays into `keyframes.json` with explicit timestamps.
2. Generate `motion.json` with stable `motion_id`.
3. Generate `scenario.json` with explicit transitions (`on_complete` or `after_seconds`).

Phase 2 SimPlayback in MuJoCo uses the same radians, `joint_order`, and `root_not_in_reference` semantics; see [06_phase2_sim_playback.md](06_phase2_sim_playback.md).

## 5) Validation (schema / contracts)

This section is **JSON schema validation** for authoring and dataset files. **Product validation** of trained policies (tracking MSE, falls, publish thresholds) is **Phase 6.1** — [12_phase6_product_validation.md](12_phase6_product_validation.md).

Reference validator implementation:

- `unitree_sdk2_python/skill_foundry_phase0/contract_validator.py`
- `unitree_sdk2_python/skill_foundry_phase0/tests/test_contract_validator.py`

The validator checks:

- required files,
- schema versions,
- units,
- strict timestamp ordering,
- tensor-like dimension consistency (`T`, `D`),
- root/base MVP constraint (`root_not_in_reference`),
- episode termination semantics in demonstrations.

## 6) Preprocessing CLI (phase 1.2)

Implementation: `unitree_sdk2_python/skill_foundry_preprocessing/cli.py`.

**Flow:** `keyframes.json` on disk → dense **`reference_trajectory.json`** (ReferenceTrajectory v1) + **`preprocess_run.json`** (reproducibility metadata).

### Commands

| Invocation | Notes |
|------------|--------|
| `skill-foundry-preprocess <path/to/keyframes.json>` | Console script (after `pip install -e .` from `unitree_sdk2_python`). |
| `python -m skill_foundry_preprocessing <path/to/keyframes.json>` | Same behavior; run with `unitree_sdk2_python` on `PYTHONPATH` or from an editable install. |

### Arguments (see `--help`)

- **positional `input`:** path to `keyframes.json` (schema `1.0.0`).
- **`-o` / `--output`:** ReferenceTrajectory JSON path. Default: **`<directory of input>/reference_trajectory.json`**.
- **`--frequency-hz`:** target sampling rate in Hz (default: **50**).
- **`--no-joint-velocities`:** omit `joint_velocities` in the trajectory file.
- **`--run-log`:** path for the run log JSON. Default: **`<directory of output>/preprocess_run.json`**.

### `preprocess_run.json` fields

| Field | Description |
|-------|-------------|
| `input_path` | Absolute path to the input keyframes file. |
| `input_sha256` | SHA-256 of the input file bytes. |
| `output_path` | Absolute path to written `reference_trajectory.json`. |
| `frequency_hz` | Same as CLI. |
| `include_joint_velocities` | `true` / `false`. |
| `timestamp_utc` | ISO 8601 UTC time when the run finished. |
| `python_version` | Short Python version string. |
| `package_name` | `unitree_sdk2py`. |
| `package_version` | Installed `unitree_sdk2py` version, or `unknown` if not installed as a package. |
| `git_commit` | *(optional)* Git `HEAD` if `git rev-parse` succeeds from a parent of the input path, or from env `GIT_COMMIT` / `SOURCE_GIT_COMMIT`. |

### Example

From the `unitree_sdk2_python` directory after editable install:

```bash
pip install -e .
skill-foundry-preprocess ./path/to/keyframes.json -o ./out/reference_trajectory.json --frequency-hz 50 --run-log ./out/preprocess_run.json
```

## 7) DemonstrationDataset from simulation (phase 2.2)

A **DemonstrationDataset v1** file can be produced by headless MuJoCo playback of `reference_trajectory.json`, recording `obs` / `act` (and optionally `ref`) at `1/sim_dt`. See [07_phase2_trajectory_recorder.md](07_phase2_trajectory_recorder.md) for `obs_schema_ref`, CLI (`skill-foundry-playback --demonstration-json`), and metadata fields (`seed`, `simulator`, `simulator_commit`).

