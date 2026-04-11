"""Ensure unitree_sdk2_python is on sys.path for imports."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_sdk_on_path(sdk_root: Path) -> None:
    root = sdk_root.resolve()
    tools = root / "tools"
    for p in (root, tools):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)
