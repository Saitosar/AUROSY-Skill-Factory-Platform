"""Discover mid_level actions (same semantics as tools/scenario_studio/runner.py)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from app.joint_map import EST_SEC_PER_KEYFRAME


@dataclass(frozen=True)
class DiscoveredAction:
    subdir: str
    action_name: str
    execute_path: str
    pose_path: str
    keyframe_count: int

    def label(self) -> str:
        return f"{self.subdir}/{self.action_name}"


def _count_keyframes(pose_path: str) -> int:
    if not os.path.isfile(pose_path):
        return 1
    try:
        with open(pose_path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 1
    if isinstance(raw, list):
        return max(1, len(raw))
    return 1


def discover_actions(sdk_root: Path) -> list[DiscoveredAction]:
    out: list[DiscoveredAction] = []
    mid = sdk_root / "mid_level_motions"
    for sub in ("basic_actions", "complex_actions"):
        base = mid / sub
        if not base.is_dir():
            continue
        for name in sorted(os.listdir(base)):
            folder = base / name
            if not folder.is_dir():
                continue
            ex = folder / "execute.py"
            if not ex.is_file():
                continue
            pose = folder / "pose.json"
            kf = _count_keyframes(str(pose))
            out.append(
                DiscoveredAction(
                    subdir=sub,
                    action_name=name,
                    execute_path=str(ex.resolve()),
                    pose_path=str(pose.resolve()) if pose.is_file() else "",
                    keyframe_count=kf,
                )
            )
    return out


def estimate_node_duration_sec(keyframe_count: int, speed: float, repeat: int) -> float:
    sp = max(0.05, float(speed))
    return float(repeat) * EST_SEC_PER_KEYFRAME * max(1, keyframe_count) / sp


def scenario_total_estimate_sec(nodes: list[dict]) -> float:
    total = 0.0
    for n in nodes:
        kc = int(n.get("keyframe_count", 1))
        if "keyframe_count" not in n and "action_name" in n:
            # legacy node without keyframe_count — use 1
            kc = 1
        sp = float(n.get("speed", 0.5))
        rep = int(n.get("repeat", 1))
        total += estimate_node_duration_sec(kc, sp, rep)
    return total


def discovered_to_json(actions: list[DiscoveredAction]) -> list[dict]:
    return [
        {
            "subdir": a.subdir,
            "action_name": a.action_name,
            "label": a.label(),
            "execute_path": a.execute_path,
            "pose_path": a.pose_path,
            "keyframe_count": a.keyframe_count,
        }
        for a in actions
    ]
