"""Ensure Unitree SDK and AUROSY Skill Foundry packages are on sys.path."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def combined_pythonpath(skill_foundry_root: Path, sdk_root: Path) -> str:
    return os.pathsep.join((str(skill_foundry_root.resolve()), str(sdk_root.resolve())))


def ensure_sdk_on_path(sdk_root: Path, skill_foundry_root: Path | None = None) -> None:
    """Insert Skill Foundry tree (and its tools/) first, then the Unitree Python SDK root."""
    paths: list[Path] = []
    if skill_foundry_root is not None:
        sf = skill_foundry_root.resolve()
        paths.extend([sf, sf / "tools"])
    paths.append(sdk_root.resolve())
    for p in paths:
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)
