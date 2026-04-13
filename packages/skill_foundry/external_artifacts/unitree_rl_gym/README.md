# Unitree RL Gym External Artifacts

This directory contains tools and data extracted from [unitree_rl_gym](https://github.com/unitreerobotics/unitree_rl_gym) for integration with the AUROSY Skill Foundry pipeline.

## Source

- **Repository:** https://github.com/unitreerobotics/unitree_rl_gym
- **Artifact:** `deploy/pre_train/g1/motion.pt`
- **Upstream commit:** `276801e46c5d` (2025-07-25)

## What is `motion.pt`?

According to the upstream README and `g1.yaml` config, `motion.pt` is a **TorchScript LSTM policy** (not a trajectory tensor). It's the pre-trained walking policy for the G1 robot exported via `PolicyExporterLSTM`.

**Key limitation:** The policy controls only **12 DOF** (legs: hip pitch/roll/yaw, knee, ankle pitch/roll × 2 legs). The full G1 robot has **29 DOF**.

## Pipeline

```
motion.pt (JIT policy)
    │
    ▼ rollout_recorder.py
rollout_12dof.npz (12 DOF trajectory)
    │
    ▼ convert_to_reference.py
reference_trajectory.json (29 DOF, ReferenceTrajectory v1)
    │
    ├─▶ For training: use as reference_path in skill-foundry-train
    │
    └─▶ convert_to_authoring.py
        keyframes.json + motion.json (authoring format for UI)
```

## Files

| File | Description |
|------|-------------|
| `motion.pt` | Original Unitree LSTM policy (TorchScript) |
| `motion_pt_inspect.json` | Inspection metadata (type, graph preview) |
| `rollout_recorder.py` | Records trajectory by running policy in MuJoCo |
| `rollout_12dof.npz` | Raw 12-DOF trajectory (250 frames @ 50Hz) |
| `rollout_12dof.meta.json` | Rollout metadata |
| `convert_to_reference.py` | Expands 12→29 DOF, outputs ReferenceTrajectory v1 |
| `reference_trajectory.json` | **Training input:** 29-DOF reference trajectory |
| `convert_to_authoring.py` | Downsamples to sparse keyframes for UI |
| `keyframes.json` | **UI input:** 10 keyframes in degrees |
| `motion.json` | Motion metadata for authoring pipeline |
| `train_config_example.yaml` | Example training config |

## Usage

### For Training (PPO tracking)

```bash
cd /path/to/AUROSY_creators_factory_platform

# Use the reference trajectory directly
skill-foundry-train \
  --reference packages/skill_foundry/external_artifacts/unitree_rl_gym/reference_trajectory.json \
  --config packages/skill_foundry/external_artifacts/unitree_rl_gym/train_config_example.yaml \
  --output-dir outputs/unitree_walking
```

### For UI / Motion Library

Copy `keyframes.json` and `motion.json` to your authoring workspace or use them as templates in the Creators Factory UI.

### Re-recording with Different Parameters

```bash
# Record longer rollout with different command velocity
python rollout_recorder.py \
  --policy motion.pt \
  --xml /path/to/scene.xml \
  --duration 20.0 \
  --hz 100

# Convert to reference
python convert_to_reference.py --input rollout_12dof.npz

# Convert to authoring (more keyframes)
python convert_to_authoring.py --keyframes 20 --motion-id my_walking_v2
```

## 12→29 DOF Mapping

The Unitree policy controls only leg joints. The converter fills remaining DOF:

| DOF Range | Joints | Source |
|-----------|--------|--------|
| 0-11 | Legs (hip, knee, ankle) | From policy rollout |
| 12-14 | Waist (yaw, roll, pitch) | Fixed at 0 |
| 15-21 | Left arm | Neutral pose (shoulder roll=0.2, elbow=0.3) |
| 22-28 | Right arm | Neutral pose (shoulder roll=-0.2, elbow=0.3) |

This is a **limitation**: the trajectory only demonstrates walking gait, not full-body motion.

## Validation

All outputs pass Phase 0 contract validation:

```bash
# Validate reference trajectory
python -c "
import json, sys
sys.path.insert(0, 'packages/skill_foundry')
from skill_foundry_phase0.contract_validator import validate_reference_trajectory_dict
ref = json.load(open('packages/skill_foundry/external_artifacts/unitree_rl_gym/reference_trajectory.json'))
errors = validate_reference_trajectory_dict(ref)
print('PASS' if not errors else errors)
"
```
