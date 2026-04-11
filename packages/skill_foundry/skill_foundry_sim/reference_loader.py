"""Load and validate ReferenceTrajectory v1 JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skill_foundry_phase0.contract_validator import validate_reference_trajectory_dict


def load_reference_trajectory_json(path: Path | str) -> dict[str, Any]:
    """
    Load reference_trajectory.json and validate ReferenceTrajectory v1 fields.
    Raises ValueError on missing file, JSON errors, or contract violations.
    """
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"reference trajectory file not found: {p}")
    try:
        payload: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {p}: {exc}") from exc

    errors = validate_reference_trajectory_dict(payload)
    if errors:
        raise ValueError("ReferenceTrajectory validation failed:\n" + "\n".join(errors))
    return payload
