"""Phase 0 JSON validation via skill_foundry_phase0."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

from app.services.sdk_path import ensure_sdk_on_path


Kind = Literal[
    "keyframes",
    "motion",
    "scenario",
    "reference_trajectory",
    "demonstration_dataset",
]


def validate_payload(
    kind: Kind,
    payload: dict[str, Any],
    sdk_root: Path,
    skill_foundry_root: Path,
) -> dict[str, Any]:
    ensure_sdk_on_path(sdk_root, skill_foundry_root)
    if "skill_foundry_phase0" not in sys.modules:
        import importlib

        importlib.invalidate_caches()
    from skill_foundry_phase0.contract_validator import (
        validate_demonstration_dataset_dict,
        validate_keyframes_dict,
        validate_motion_dict,
        validate_reference_trajectory_dict,
        validate_scenario_dict,
    )

    errors: list[str]
    if kind == "keyframes":
        errors = validate_keyframes_dict(payload)
    elif kind == "motion":
        errors = validate_motion_dict(payload)
    elif kind == "scenario":
        errors = validate_scenario_dict(payload)
    elif kind == "reference_trajectory":
        errors = validate_reference_trajectory_dict(payload)
    elif kind == "demonstration_dataset":
        errors = validate_demonstration_dataset_dict(payload)
    else:
        errors = [f"unknown kind: {kind}"]

    return {"ok": not errors, "errors": errors}
