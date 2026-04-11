"""
Экспорт действий Pose Studio: mid_level_motions/basic_actions|complex_actions/<name>/
"""

import json
import os
from typing import Dict, List, Optional, Tuple

from core_control.config.joint_limits import get_limit
from core_control.joint_controller import JointController
from skill_generator import to_class_name, validate_skill_name

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)


def _mid_level_root() -> str:
    return os.path.join(_REPO_ROOT, "mid_level_motions")


EXECUTE_PY_TEMPLATE = '''"""
SAI Motion Builder: __ACTION_NAME__ (сгенерировано Pose Studio).
Фазы на каждый кадр: левая нога → правая нога → руки → талия.
Углы в pose.json (градусы); расчёты — в радианах (clamp_q).
Переопределение скоростей (рад/с): опционально speed_overrides.json; без файла — как раньше.
"""

import json
import math
import os
import sys
import time
from typing import Dict, List, Optional, Set

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.normpath(os.path.join(current_dir, "..", "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core_control.config.joint_limits import clamp_q, get_limit
from core_control.joint_controller import JointController
from core_control.low_level_motions.atomic_move import AtomicMove
from core_control.utils.conversions import deg2rad, rad2deg

LEFT_LEG: List[int] = list(range(0, 6))
RIGHT_LEG: List[int] = list(range(6, 12))
WAIST: List[int] = list(range(12, 15))
ARMS: List[int] = list(range(15, 29))

_DT = 0.005


def _load_speed_overrides() -> Dict[int, float]:
    """Опционально: speed_overrides.json рядом с pose.json (рад/с на сустав)."""
    path = os.path.join(current_dir, "speed_overrides.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        return {}
    out: Dict[int, float] = {}
    for k, v in raw.items():
        try:
            jid = int(k)
            out[jid] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _load_poses_deg() -> List[Dict[int, float]]:
    path = os.path.join(current_dir, "pose.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        out: List[Dict[int, float]] = []
        for item in raw:
            out.append({int(k): float(v) for k, v in item.items()})
        return out
    return [{int(k): float(v) for k, v in raw.items()}]


def _ensure_all_joints(pose: Dict[int, float]) -> Dict[int, float]:
    for jid in JointController.JOINT_MAP:
        if jid not in pose:
            pose[jid] = 0.0
    return pose


class __CLASS_NAME__:
    """Фазовое движение по ключевым кадрам (логика как в arms_on_waist)."""

    def __init__(self, move_node: Optional[AtomicMove] = None) -> None:
        print("[SAI Action] __ACTION_NAME__ — инициализация…")
        if move_node is not None:
            self.move_node = move_node
            self.ctrl = move_node.ctrl
            self.listener = move_node.listener
        else:
            self.move_node = AtomicMove()
            self.ctrl = self.move_node.ctrl
            self.listener = self.move_node.listener
        self._speed_overrides = _load_speed_overrides()

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
            base = self._speed_overrides.get(jid, speed)
            safe_speed = min(lim["max_vel"], base)
            dist = abs(target_q - start_q)
            duration = dist / safe_speed if safe_speed > 0 else 0.1
            steps = max(1, int(duration / _DT))

            print(
                f"[SAI Action] Нога: сустав {jid} ({lim['name']}) "
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
            q_req = deg2rad(targets_deg[jid])
            targets_rad[jid] = clamp_q(jid, q_req)

        start: Dict[int, float] = {jid: fixed_rad[jid] for jid in joint_ids}
        distances = [abs(targets_rad[jid] - start[jid]) for jid in joint_ids]
        durations: List[float] = []
        for i, jid in enumerate(joint_ids):
            lim = get_limit(jid)
            base = self._speed_overrides.get(jid, speed)
            cap = min(lim["max_vel"], base)
            dist = distances[i]
            d = dist / cap if cap > 0 else 0.1
            durations.append(d)
        duration = max(durations) if durations else 0.1
        steps = max(1, int(duration / _DT))

        print(
            f"[SAI Action] Параллельно суставы {joint_ids[0]}…{joint_ids[-1]} "
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

    def _move_to_pose(
        self,
        targets_deg: Dict[int, float],
        speed: float,
        fixed_rad: Dict[int, float],
        kf_index: int,
        kf_total: int,
    ) -> None:
        locked: Set[int] = set()
        print(f"[SAI Action] Кадр {kf_index}/{kf_total}: фаза 1 — левая нога…")
        self._sequential_leg_joints(LEFT_LEG, targets_deg, speed, fixed_rad, locked)
        print(f"[SAI Action] Кадр {kf_index}/{kf_total}: фаза 2 — правая нога…")
        self._sequential_leg_joints(RIGHT_LEG, targets_deg, speed, fixed_rad, locked)
        print(f"[SAI Action] Кадр {kf_index}/{kf_total}: фаза 3 — обе руки…")
        self._smooth_parallel(ARMS, targets_deg, speed, fixed_rad)
        print(f"[SAI Action] Кадр {kf_index}/{kf_total}: фаза 4 — талия…")
        self._smooth_parallel(WAIST, targets_deg, speed, fixed_rad)

    def execute(self, speed: float = 0.5, hold_at_end: bool = True) -> None:
        raw_poses = _load_poses_deg()
        if not raw_poses:
            print("[SAI Action] Ошибка: pose.json пуст или отсутствует.")
            return
        poses = [_ensure_all_joints(dict(p)) for p in raw_poses]
        fixed_rad = self._snapshot_rad()
        n = len(poses)
        for i, targets_deg in enumerate(poses):
            self._move_to_pose(targets_deg, speed, fixed_rad, i + 1, n)

        last = poses[-1]
        if not hold_at_end:
            return
        print("\\n[SAI SUCCESS] Последняя поза достигнута. Удержание + Ctrl+C для выхода.")
        try:
            while True:
                for jid in JointController.JOINT_MAP:
                    self.ctrl.set_joint_deg(jid, last[jid])
                self.ctrl.publish()
                time.sleep(0.01)
        except KeyboardInterrupt:
            print("\\n[SAI Action] Остановлено пользователем.")


if __name__ == "__main__":
    __CLASS_NAME__().execute(hold_at_end=True)
'''


def save_action(
    action_name: str,
    frames_deg: List[Dict[int, float]],
    motor_speed_overrides: Optional[Dict[int, float]] = None,
) -> Tuple[str, str]:
    """
    Пишет mid_level_motions/basic_actions/<name>/ или complex_actions/<name>/
    в зависимости от числа кадров (1 vs 2–3).

    При непустом motor_speed_overrides дополнительно пишет speed_overrides.json (рад/с).

    Возвращает (каталог действия, путь к execute.py).
    """
    ok, name_or_err = validate_skill_name(action_name)
    if not ok:
        raise ValueError(name_or_err)
    name = name_or_err
    if not frames_deg:
        raise ValueError("Нет кадров для сохранения.")

    n = len(frames_deg)
    subdir = "basic_actions" if n == 1 else "complex_actions"
    action_dir = os.path.join(_mid_level_root(), subdir, name)
    os.makedirs(action_dir, exist_ok=True)

    def _frame_json(frame: Dict[int, float]) -> Dict[str, float]:
        return {
            str(jid): round(float(frame.get(jid, 0.0)), 6)
            for jid in sorted(JointController.JOINT_MAP.keys())
        }

    if n == 1:
        pose_payload: object = _frame_json(frames_deg[0])
    else:
        pose_payload = [_frame_json(frame) for frame in frames_deg]

    pose_path = os.path.join(action_dir, "pose.json")
    with open(pose_path, "w", encoding="utf-8") as f:
        json.dump(pose_payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    spd_path = os.path.join(action_dir, "speed_overrides.json")
    if motor_speed_overrides:
        filtered: Dict[str, float] = {}
        for jid, v in motor_speed_overrides.items():
            if jid not in JointController.JOINT_MAP:
                continue
            vv = max(0.0, min(float(v), float(get_limit(jid)["max_vel"])))
            filtered[str(jid)] = round(vv, 6)
        if filtered:
            with open(spd_path, "w", encoding="utf-8") as f:
                json.dump(filtered, f, indent=2, ensure_ascii=False)
                f.write("\n")
        elif os.path.isfile(spd_path):
            try:
                os.remove(spd_path)
            except OSError:
                pass
    elif os.path.isfile(spd_path):
        try:
            os.remove(spd_path)
        except OSError:
            pass

    cls = to_class_name(name)
    execute_src = (
        EXECUTE_PY_TEMPLATE.replace("__ACTION_NAME__", name)
        .replace("__CLASS_NAME__", cls)
    )
    execute_path = os.path.join(action_dir, "execute.py")
    with open(execute_path, "w", encoding="utf-8") as f:
        f.write(execute_src)

    return action_dir, execute_path
