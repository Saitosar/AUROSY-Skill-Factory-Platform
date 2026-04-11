"""Validate export manifest dict against JSON Schema (optional ``jsonschema``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_manifest_schema_path() -> Path:
    """Path to ``export_manifest.schema.json`` in the repository docs."""
    # packages/skill_foundry/skill_foundry_export/validate.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3] / "docs" / "skill_foundry" / "contracts" / "export" / "export_manifest.schema.json"


def validate_export_manifest_dict(data: dict[str, Any]) -> list[str]:
    """
    Return a list of validation error strings; empty if valid.

    If ``jsonschema`` is not installed, returns an empty list (skip validation).
    """
    try:
        import jsonschema
    except ImportError:
        return []

    schema_path = export_manifest_schema_path()
    if not schema_path.is_file():
        return [f"schema file not found: {schema_path}"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errs: list[str] = []
    validator = jsonschema.Draft202012Validator(schema)
    for e in validator.iter_errors(data):
        errs.append(f"{e.json_path}: {e.message}")
    return errs
