# Phase 0 acceptance checklist

Use this checklist before starting Phase 1 preprocessing implementation.

## Required checks

- [x] Authoring schemas are defined:
  - `docs/skill_foundry/contracts/authoring/keyframes.schema.json`
  - `docs/skill_foundry/contracts/authoring/motion.schema.json`
  - `docs/skill_foundry/contracts/authoring/scenario.schema.json`
- [x] Training schemas are defined:
  - `docs/skill_foundry/contracts/training/reference_trajectory.schema.json`
  - `docs/skill_foundry/contracts/training/demonstration_dataset.schema.json`
- [x] Valid and invalid examples exist for each contract format.
- [x] MVP root/base model is fixed to `root_not_in_reference`.
- [x] Canonical joint order source is documented (`JointController.JOINT_MAP`).
- [x] Golden bundle exists in `docs/skill_foundry/golden/v1`.
- [x] Validator script exists:
  - `unitree_sdk2_python/skill_foundry_phase0/validate_phase0_contracts.py`
- [x] Automated tests exist:
  - `unitree_sdk2_python/skill_foundry_phase0/tests/test_contract_validator.py`

## Verification commands

```bash
python3 -m unittest unitree_sdk2_python/skill_foundry_phase0/tests/test_contract_validator.py
PYTHONPATH=unitree_sdk2_python python3 unitree_sdk2_python/skill_foundry_phase0/validate_phase0_contracts.py --bundle-dir docs/skill_foundry/golden/v1
```

Both commands must pass before Phase 1 work starts.

