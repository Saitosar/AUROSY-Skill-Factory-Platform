# Skill Foundry: Phase 2 — Trajectory recorder (DemonstrationDataset v1)

This document specifies task **2.2** from [03_implementation_plan.md](03_implementation_plan.md): recording **observations** and **actions** at the simulation rate into **DemonstrationDataset v1** while playing a **ReferenceTrajectory** in MuJoCo (same pipeline as [06_phase2_sim_playback.md](06_phase2_sim_playback.md)).

## Role in the pipeline

After headless playback ([task 2.1](06_phase2_sim_playback.md)), the recorder produces `demonstration_dataset.json` for offline imitation / hybrid training, aligned with the training contract in [04_phase0_contracts.md](04_phase0_contracts.md) §2 and the JSON schema [contracts/training/demonstration_dataset.schema.json](contracts/training/demonstration_dataset.schema.json).

## Semantics: `obs_schema_ref`

Stable id: **`skill_foundry_sim_motor_q_dq_ctrl_v1`**.

| Segment | Length | Meaning |
|---------|--------|---------|
| `obs` | 58 | Concatenation of measured motor joint positions **q** (29) then velocities **dq** (29), **motor index order** 0…28 (same as `JointController.JOINT_MAP` / MJCF actuators). |
| `act` | 29 | MuJoCo `ctrl` torques at the same step (PD output in **dynamic** mode; zeros in **kinematic** mode). |
| `ref` | 29 (optional) | Interpolated reference joint targets **q_des** in motor index order (omitted if `--no-ref`). |
| `done` | — | `false` on all steps except the **last** step of the episode (`true`). |

**Sampling rate:** `sampling_hz = 1 / sim_dt` (e.g. 200 Hz for `dt = 0.005`).

**Metadata (dataset root):**

- `robot_model` — from the reference file when present (default `g1_29dof`).
- `seed` — playback seed.
- `simulator` — string `mujoco <mujoco.__version__>`.
- `simulator_commit` — Git `HEAD` when available (same resolution as preprocess: env `GIT_COMMIT` / `SOURCE_GIT_COMMIT`, or `git rev-parse` from an ancestor of the MJCF / reference path).

Validation API: `skill_foundry_phase0.contract_validator.validate_demonstration_dataset_dict`.

## Implementation

- Package: `packages/skill_foundry/skill_foundry_sim/`
- `headless_playback.PlaybackLog` includes `motor_q`, `motor_dq`, `reference_motor_q`, and `ctrl` for each simulation step.
- `demonstration_dataset.build_demonstration_dataset` assembles the JSON object; `write_demonstration_dataset_json` writes the file.

## CLI

Use the same entry point as playback, with optional demonstration output:

```bash
skill-foundry-playback path/to/reference_trajectory.json \
  --mjcf /path/to/unitree_mujoco/unitree_robots/g1/scene_29dof.xml \
  --mode dynamic \
  --dt 0.005 \
  --seed 0 \
  -o /tmp/playback_log.npz \
  --demonstration-json /tmp/demonstration_dataset.json
```

Options:

- `--demonstration-json PATH` — write DemonstrationDataset v1 JSON.
- `--no-ref` — omit per-step `ref` arrays.
- `--episode-id ID` — default `ep_0001`.

Stdout JSON includes `demonstration_dataset` and `obs_schema_ref` when `--demonstration-json` is set.

## DoD (task 2.2)

The written file passes `validate_demonstration_dataset_dict` with no errors; dimensions and `obs_schema_ref` match the table above so a training script can load episodes without manual fixes.

## Limitations (MVP)

- Large trajectories produce large JSON files; binary export (e.g. `.npz` / HDF5) can be added later without changing the logical contract.
- RL workers must use the same `obs_schema_ref` and observation layout when consuming this dataset.

## Related documents

- [06_phase2_sim_playback.md](06_phase2_sim_playback.md) — playback modes and PD law.
- [04_phase0_contracts.md](04_phase0_contracts.md) — training contract overview.
- [02_architecture.md](02_architecture.md) — Trajectory recorder module.
