# Skill Foundry: Phase 2 — SimPlayback (ReferenceTrajectory in MuJoCo)

This document specifies task **2.1** from [03_implementation_plan.md](03_implementation_plan.md): playing a dense **ReferenceTrajectory v1** in the Unitree G1 MuJoCo model used in this repository.

## Role in the pipeline

Matches the optional branch in [02_architecture.md](02_architecture.md): **Artifact store → SimPlayback → Trajectory recorder** (recorder is task 2.2).

**Inputs:** `reference_trajectory.json` (same contract as Phase 0 / Phase 1 output).

**Outputs:** visualization in MuJoCo (when using `unitree_mujoco` with DDS) or a **deterministic headless log** (`.npz`) for regression checks.

## Joint and unit alignment

- Angles are **radians**; time is **seconds**; `joint_order` uses numeric strings `"0"`…`"28"` as in [04_phase0_contracts.md](04_phase0_contracts.md) §3 (canonical G1 29‑DoF map).
- MuJoCo actuator order in `unitree_mujoco/unitree_robots/g1/g1_29dof.xml` matches that map (motor index = contract index).
- **Root / base:** MVP remains `root_not_in_reference` — the floating base is **not** driven by the reference file; it follows simulation physics (and default initial pose after `mj_resetData`).

## Time discretization: `frequency_hz` vs simulation `dt`

The reference is sampled at `frequency_hz`. The simulator steps at `sim_dt` (e.g. `0.005` s in [unitree_mujoco/simulate_python/config.py](../../unitree_mujoco/simulate_python/config.py)).

**Rule implemented in code:** at each simulation step at time `t_k = k * sim_dt`, target joint columns are obtained by **linear interpolation in time** between the two surrounding reference rows (see `skill_foundry_sim.trajectory_sampler.sample_trajectory_at_times`). If playback continues past the last reference sample time, targets are **clamped** to the last row.

This rule must stay fixed for reproducible logs.

## Modes

| Mode | Behavior | Use |
|------|-----------|-----|
| **dynamic** (default) | PD torque like `unitree_mujoco` Python bridge: `ctrl = kp*(q_des - q_meas) + kd*(dq_des - dq_meas)` on jointpos/jointvel sensors | Default for task 2.1 DoD, task 2.2 demos, RL-aligned rollout |
| **kinematic** | Writes hinge `qpos` from the trajectory and calls `mj_forward` only (no `mj_step`) | Fast pose preview; **not** a physically rolled-out trajectory |

For motors whose indices are **not** listed in `joint_order`, **dynamic** mode keeps their targets equal to the **current** simulated joint positions (hold current pose).

## Implementation (headless)

Package: `packages/skill_foundry/skill_foundry_sim/`

- `reference_loader.load_reference_trajectory_json` — loads JSON and validates via `skill_foundry_phase0.contract_validator.validate_reference_trajectory_dict`.
- `run_headless_playback` — MuJoCo load, interpolation, dynamic or kinematic loop, returns `PlaybackLog` (`time_s`, `motor_q`, `ctrl`).
- `log_compare.compare_playback_logs` — compares two logs with `numpy.allclose` (tunable `atol` / `rtol`).

**Reproducibility:** With the same `reference_trajectory.json`, `mjcf` path, `sim_dt`, mode, `kp`/`kd` (dynamic), `seed`, and `max_steps`, two headless runs produce **bitwise-identical** logs on a fixed machine (tests use tight tolerances).

## CLI

After `pip install -e "./unitree_sdk2_python"` and `pip install -e "./packages/skill_foundry"` from the **platform repo root**:

```bash
skill-foundry-playback path/to/reference_trajectory.json \
  --mjcf /path/to/unitree_mujoco/unitree_robots/g1/scene_29dof.xml \
  --mode dynamic \
  --dt 0.005 \
  --kp 150 --kd 5 \
  --seed 0 \
  -o /tmp/playback_log.npz
```

Optional: `--compare other.npz` exits with status 1 if logs differ.

Console output includes JSON metadata (`mujoco_version`, paths, gains, etc.).

**Demonstration recording (task 2.2):** add `--demonstration-json /path/to/demonstration_dataset.json` to write **DemonstrationDataset v1** (optional `--no-ref`, `--episode-id`). Specification: [07_phase2_trajectory_recorder.md](07_phase2_trajectory_recorder.md).

## Live simulation with `unitree_mujoco` (dynamic)

1. Start the Python simulator so the DDS bridge listens on `rt/lowcmd` (see [unitree_mujoco/readme.md](../../unitree_mujoco/readme.md)).
2. Run a publisher that sends `LowCmd` at the simulation rate with the same PD law and interpolated targets as above. The headless module documents the intended control law; wiring a separate publisher script is optional and should keep gains and interpolation identical for parity.

## Limitations (MVP)

- Single `reference_trajectory.json` per run; **scenario chains** are out of scope until preprocessing or tooling concatenates trajectories.
- RL training environment MJCF must be **aligned** with this scene for sim2sim; document versions when adding RL workers.

## Related documents

- [04_phase0_contracts.md](04_phase0_contracts.md) — ReferenceTrajectory v1 fields.
- [07_phase2_trajectory_recorder.md](07_phase2_trajectory_recorder.md) — DemonstrationDataset v1 from playback (task 2.2).
- [03_implementation_plan.md](03_implementation_plan.md) — tasks 2.1–2.2.
