"""
Генерация пакета навыка: library/skills/<name>/pose.json + execute.py
"""

import json
import os
import re
from typing import Dict, Tuple

# Корень unitree_sdk2_python (родитель каталога tools/)
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)


def validate_skill_name(name: str) -> Tuple[bool, str]:
    name = (name or "").strip()
    if not name:
        return False, "Введите имя навыка (например, greet_v1)."
    if ".." in name or "/" in name or "\\" in name:
        return False, "Недопустимые символы в имени."
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", name):
        return (
            False,
            "Имя: латиница, цифры, подчёркивание; первый символ — буква.",
        )
    return True, name


def to_class_name(skill_name: str) -> str:
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", skill_name) if p]
    if not parts:
        return "GeneratedSkill"
    return "".join(p.capitalize() for p in parts) + "Skill"


def format_pose_deg_dict(pose: Dict[int, float]) -> str:
    lines = [f"    {jid}: {pose[jid]!r}," for jid in sorted(pose.keys())]
    return "\n".join(lines)


EXECUTE_PY_TEMPLATE = '''"""
SAI skill: __SKILL_NAME__ (сгенерировано Pose Studio).
Фазы: левая нога → правая нога → обе руки параллельно → талия.
Углы: pose.json рядом со скриптом или встроенный POSE_DEG.
"""

import json
import math
import os
import sys
import time
from typing import Dict, List, Optional, Set

current_dir = os.path.dirname(os.path.abspath(__file__))
# library/skills/<name>/ → unitree_sdk2_python
root_dir = os.path.normpath(os.path.join(current_dir, "..", "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core_control.config.joint_limits import clamp_q, get_limit
from core_control.joint_controller import JointController
from core_control.low_level_motions.atomic_move import AtomicMove
from core_control.utils.conversions import deg2rad, rad2deg

POSE_DEG: Dict[int, float] = {
__POSE_DEG_BODY__
}

LEFT_LEG: List[int] = list(range(0, 6))
RIGHT_LEG: List[int] = list(range(6, 12))
WAIST: List[int] = list(range(12, 15))
ARMS: List[int] = list(range(15, 29))

_DT = 0.005


def _load_pose_deg() -> Dict[int, float]:
    path = os.path.join(current_dir, "pose.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {int(k): float(v) for k, v in raw.items()}
    return dict(POSE_DEG)


def _ensure_all_joints(pose: Dict[int, float]) -> Dict[int, float]:
    for jid in JointController.JOINT_MAP:
        if jid not in pose:
            pose[jid] = 0.0
    return pose


class __CLASS_NAME__:
    """Фазовое движение к целевой позе (JointController / clamp_q)."""

    def __init__(self, move_node: Optional[AtomicMove] = None) -> None:
        print("[SAI Skill] __SKILL_NAME__ — инициализация…")
        if move_node is not None:
            self.move_node = move_node
            self.ctrl = move_node.ctrl
            self.listener = move_node.listener
        else:
            self.move_node = AtomicMove()
            self.ctrl = self.move_node.ctrl
            self.listener = self.move_node.listener

    def _snapshot_rad(self) -> Dict[int, float]:
        out: Dict[int, float] = {}
        for jid in JointController.JOINT_MAP:
            q = self.listener.get_joint_pos(jid)
            out[jid] = q if q is not None else 0.0
        return out

    def _sequential_leg_joints(
        self,
        order: List[int],
        targets_deg: Dict[int, float],
        speed: float,
        fixed_rad: Dict[int, float],
        locked: Set[int],
    ) -> None:
        initial = dict(fixed_rad)
        for jid in order:
            lim = get_limit(jid)
            target_q = clamp_q(jid, deg2rad(targets_deg[jid]))
            start_q = fixed_rad[jid]
            safe_speed = min(lim["max_vel"], speed)
            dist = abs(target_q - start_q)
            duration = dist / safe_speed if safe_speed > 0 else 0.1
            steps = max(1, int(duration / _DT))

            print(
                f"[SAI Skill] Нога: {jid} ({lim['name']}) "
                f"{rad2deg(start_q):.1f}° → {rad2deg(target_q):.1f}° (~{duration:.2f}s)"
            )

            for i in range(steps + 1):
                t = i / steps
                smooth_t = (1.0 - math.cos(t * math.pi)) / 2.0
                q_j = start_q + (target_q - start_q) * smooth_t
                for k in JointController.JOINT_MAP:
                    if k in locked:
                        self.ctrl.set_joint(k, fixed_rad[k])
                    elif k == jid:
                        self.ctrl.set_joint(k, q_j)
                    else:
                        self.ctrl.set_joint(k, initial[k])
                self.ctrl.publish()
                time.sleep(_DT)

            fixed_rad[jid] = target_q
            locked.add(jid)

    def _smooth_parallel(
        self,
        joint_ids: List[int],
        targets_deg: Dict[int, float],
        speed: float,
        fixed_rad: Dict[int, float],
    ) -> None:
        targets_rad: Dict[int, float] = {}
        for jid in joint_ids:
            targets_rad[jid] = clamp_q(jid, deg2rad(targets_deg[jid]))

        start = {jid: fixed_rad[jid] for jid in joint_ids}
        max_vel = min(get_limit(jid)["max_vel"] for jid in joint_ids)
        safe_speed = min(max_vel, speed)
        distances = [abs(targets_rad[jid] - start[jid]) for jid in joint_ids]
        max_dist = max(distances) if distances else 0.0
        duration = max_dist / safe_speed if safe_speed > 0 else 0.1
        steps = max(1, int(duration / _DT))

        print(
            f"[SAI Skill] Параллельно {joint_ids[0]}…{joint_ids[-1]} "
            f"(N={len(joint_ids)}), ~{duration:.2f}s"
        )

        for i in range(steps + 1):
            t = i / steps
            smooth_t = (1.0 - math.cos(t * math.pi)) / 2.0
            for jid in JointController.JOINT_MAP:
                if jid in joint_ids:
                    q = start[jid] + (targets_rad[jid] - start[jid]) * smooth_t
                    self.ctrl.set_joint(jid, q)
                else:
                    self.ctrl.set_joint(jid, fixed_rad[jid])
            self.ctrl.publish()
            time.sleep(_DT)

        for jid in joint_ids:
            fixed_rad[jid] = targets_rad[jid]

    def execute(self, speed: float = 0.5) -> None:
        targets_deg = _ensure_all_joints(_load_pose_deg())
        fixed_rad = self._snapshot_rad()
        locked: Set[int] = set()

        print("[SAI Skill] Фаза 1: левая нога…")
        self._sequential_leg_joints(LEFT_LEG, targets_deg, speed, fixed_rad, locked)

        print("[SAI Skill] Фаза 2: правая нога…")
        self._sequential_leg_joints(RIGHT_LEG, targets_deg, speed, fixed_rad, locked)

        print("[SAI Skill] Фаза 3: обе руки…")
        self._smooth_parallel(ARMS, targets_deg, speed, fixed_rad)

        print("[SAI Skill] Фаза 4: талия…")
        self._smooth_parallel(WAIST, targets_deg, speed, fixed_rad)

        print("\\n[SAI SUCCESS] Поза достигнута. Ctrl+C для выхода.")
        try:
            while True:
                for jid in JointController.JOINT_MAP:
                    self.ctrl.set_joint_deg(jid, targets_deg[jid])
                self.ctrl.publish()
                time.sleep(0.01)
        except KeyboardInterrupt:
            print("\\n[SAI Skill] Остановлено.")


if __name__ == "__main__":
    __CLASS_NAME__().execute()
'''


def export_skill(skill_name: str, pose_deg: Dict[int, float]) -> Tuple[str, str]:
    """
    Создаёт library/skills/<skill_name>/pose.json и execute.py.
    Возвращает (путь к папке навыка, путь к execute.py).
    """
    ok, name_or_err = validate_skill_name(skill_name)
    if not ok:
        raise ValueError(name_or_err)
    name = name_or_err

    skill_dir = os.path.join(_REPO_ROOT, "library", "skills", name)
    os.makedirs(skill_dir, exist_ok=True)

    pose_path = os.path.join(skill_dir, "pose.json")
    pose_for_json = {str(jid): round(pose_deg[jid], 6) for jid in sorted(pose_deg.keys())}
    with open(pose_path, "w", encoding="utf-8") as f:
        json.dump(pose_for_json, f, indent=2, ensure_ascii=False)
        f.write("\n")

    body = format_pose_deg_dict(pose_deg)
    execute_src = (
        EXECUTE_PY_TEMPLATE.replace("__SKILL_NAME__", name)
        .replace("__CLASS_NAME__", to_class_name(name))
        .replace("__POSE_DEG_BODY__", body)
    )

    execute_path = os.path.join(skill_dir, "execute.py")
    with open(execute_path, "w", encoding="utf-8") as f:
        f.write(execute_src)

    return skill_dir, execute_path
