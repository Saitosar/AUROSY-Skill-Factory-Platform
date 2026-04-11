"""
Загрузка и исполнение сценариев (ноды = действия из basic_actions / complex_actions).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Type

# Пакет: tools/scenario_studio/runner.py → repo root = ../..
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_PKG_DIR)
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)

if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from core_control.low_level_motions.atomic_move import AtomicMove
from skill_generator import to_class_name

SCENARIO_VERSION = 1

# Эвристика длительности одного keyframe при speed=1.0 (сек), для UI timeline.
EST_SEC_PER_KEYFRAME = 8.0

_mod_load_seq = 0


def repo_root() -> str:
    return _REPO_ROOT


def mid_level_motions_root() -> str:
    return os.path.join(_REPO_ROOT, "mid_level_motions")


def high_level_motions_root() -> str:
    return os.path.join(_REPO_ROOT, "high_level_motions")


@dataclass(frozen=True)
class DiscoveredAction:
    subdir: str  # basic_actions | complex_actions
    action_name: str
    execute_path: str
    pose_path: str
    keyframe_count: int

    @property
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


def discover_actions() -> List[DiscoveredAction]:
    """Папки с execute.py под basic_actions и complex_actions."""
    out: List[DiscoveredAction] = []
    mid = mid_level_motions_root()
    for sub in ("basic_actions", "complex_actions"):
        base = os.path.join(mid, sub)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            folder = os.path.join(base, name)
            if not os.path.isdir(folder):
                continue
            ex = os.path.join(folder, "execute.py")
            if not os.path.isfile(ex):
                continue
            pose = os.path.join(folder, "pose.json")
            kf = _count_keyframes(pose)
            out.append(
                DiscoveredAction(
                    subdir=sub,
                    action_name=name,
                    execute_path=ex,
                    pose_path=pose,
                    keyframe_count=kf,
                )
            )
    return out


def estimate_node_duration_sec(
    keyframe_count: int, speed: float, repeat: int
) -> float:
    sp = max(0.05, float(speed))
    return float(repeat) * EST_SEC_PER_KEYFRAME * max(1, keyframe_count) / sp


def load_skill_class(execute_py_path: str, action_folder_name: str) -> Type[Any]:
    global _mod_load_seq
    _mod_load_seq += 1
    mod_name = f"_scenario_skill_{_mod_load_seq}_{action_folder_name}"
    spec = importlib.util.spec_from_file_location(mod_name, execute_py_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить модуль: {execute_py_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cls_name = to_class_name(action_folder_name)
    if hasattr(mod, cls_name):
        return getattr(mod, cls_name)

    for attr in dir(mod):
        if attr.endswith("Skill"):
            obj = getattr(mod, attr)
            if isinstance(obj, type):
                return obj

    raise AttributeError(
        f"В {execute_py_path} не найден класс {cls_name} и ни одного *Skill."
    )


def _node_execute_path(subdir: str, action_name: str) -> str:
    return os.path.join(
        mid_level_motions_root(), subdir, action_name, "execute.py"
    )


def run_scenario(
    data: Dict[str, Any],
    *,
    on_step: Optional[
        Callable[[int, int, int, str], None]
    ] = None,
    stop_event: Optional[Event] = None,
    hold_last_node: bool = False,
) -> None:
    """
    data: scenario.json (version, title, nodes[]).

    on_step(node_index, repeat_index, repeat_total, label)
    hold_last_node: удержание только после последнего повтора последней ноды —
      для CLI / run.py.
    """
    if int(data.get("version", 0)) != SCENARIO_VERSION:
        raise ValueError(f"Ожидался version={SCENARIO_VERSION} в scenario.json")

    nodes_raw = data.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        print("[Scenario] Пустой список нод.")
        return

    nodes: List[Dict[str, Any]] = []
    for item in nodes_raw:
        if not isinstance(item, dict):
            continue
        sub = item.get("subdir")
        an = item.get("action_name")
        if sub not in ("basic_actions", "complex_actions") or not an:
            continue
        speed = float(item.get("speed", 0.5))
        repeat = max(1, int(item.get("repeat", 1)))
        nodes.append(
            {
                "subdir": sub,
                "action_name": str(an),
                "speed": speed,
                "repeat": repeat,
            }
        )

    if not nodes:
        print("[Scenario] Нет валидных нод.")
        return

    shared_move = AtomicMove(print_initial_state=False)
    n_nodes = len(nodes)
    for ni, node in enumerate(nodes):
        ex_path = _node_execute_path(node["subdir"], node["action_name"])
        if not os.path.isfile(ex_path):
            print(f"[Scenario] Нет файла: {ex_path}")
            return

        label = f"{node['subdir']}/{node['action_name']}"
        skill_cls = load_skill_class(ex_path, node["action_name"])
        repeat = node["repeat"]
        is_last = ni == n_nodes - 1

        for r in range(repeat):
            if stop_event is not None and stop_event.is_set():
                print("[Scenario] Останов по запросу (между нодами).")
                return
            if on_step is not None:
                on_step(ni, r + 1, repeat, label)
            print(
                f"[Scenario] Нода {ni + 1}/{n_nodes} «{label}» "
                f"повтор {r + 1}/{repeat} speed={node['speed']}"
            )
            skill = skill_cls(move_node=shared_move)
            last_rep = r == repeat - 1
            hold_this = hold_last_node and is_last and last_rep
            skill.execute(speed=node["speed"], hold_at_end=hold_this)


def run_scenario_from_path(
    scenario_json_path: str,
    *,
    stop_event: Optional[Event] = None,
    on_step: Optional[Callable[[int, int, int, str], None]] = None,
    hold_last_node: bool = True,
) -> None:
    """Запуск из CLI / run.py: удержание последней позы после сценария."""
    path = os.path.abspath(scenario_json_path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    run_scenario(
        data,
        stop_event=stop_event,
        on_step=on_step,
        hold_last_node=hold_last_node,
    )


def scenario_total_estimate_sec(nodes: List[Dict[str, Any]]) -> float:
    """Суммарная эвристика по списку нод (как в UI)."""
    disc = {d.label: d for d in discover_actions()}
    total = 0.0
    for node in nodes:
        sub = node.get("subdir")
        an = node.get("action_name")
        if sub not in ("basic_actions", "complex_actions") or not an:
            continue
        key = f"{sub}/{an}"
        d = disc.get(key)
        kf = d.keyframe_count if d else 1
        total += estimate_node_duration_sec(
            kf, float(node.get("speed", 0.5)), int(node.get("repeat", 1))
        )
    return total
