"""
Поза из Pose Studio (Save Pose): робот плавно выходит на целевые углы.

Порядок:
  1) Левая нога — суставы 0→5 по одному (каждый следующий при удержании предыдущих).
  2) Правая нога — 6→11 так же.
  3) Обе руки — суставы 15–28 одним синхронным движением.
  4) Талия — 12–14 одним синхронным движением (последней).

Цели в градусах: POSE_DEG ниже или файл arms_on_waist_pose_deg.json (рядом со скриптом).
JSON из терминала (ключи-строки) подходит: скопируйте в .json или переведите ключи в int в POSE_DEG.
"""

import json
import math
import os
import sys
import time
from typing import Dict, List, Set

# Подключение путей платформы SAI
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from core_control.config.joint_limits import clamp_q, get_limit
from core_control.joint_controller import JointController
from core_control.low_level_motions.atomic_move import AtomicMove
from core_control.utils.conversions import deg2rad, rad2deg

# --- Целевая поза (градусы, индекс = joint_id как в JointController.JOINT_MAP) ---
# Снято из Pose Studio → Save Pose. Файл arms_on_waist_pose_deg.json перекрывает эти значения.
POSE_DEG: Dict[int, float] = {
    0: 1.0,
    1: 4.0,
    2: 10.0,
    3: 10.0,
    4: -8.5,
    5: 0.0193,
    6: 0.5,
    7: 0.0,
    8: -10.0,
    9: 10.0,
    10: -8.5,
    11: -0.0569,
    12: -1.0,
    13: 0.2,
    14: 0.2,
    15: -3.5,
    16: 56.0,
    17: -71.0,
    18: -5.5,
    19: -0.5,
    20: 1.0,
    21: 5.0,
    22: -3.5,
    23: -56.0,
    24: 71.0,
    25: -5.5,
    26: 0.5,
    27: -2.0,
    28: 5.0,
}

LEFT_LEG: List[int] = list(range(0, 6))
RIGHT_LEG: List[int] = list(range(6, 12))
WAIST: List[int] = list(range(12, 15))
ARMS: List[int] = list(range(15, 29))

_DT = 0.005


def _load_pose_deg() -> Dict[int, float]:
    path = os.path.join(current_dir, "arms_on_waist_pose_deg.json")
    if not os.path.isfile(path):
        return dict(POSE_DEG)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out: Dict[int, float] = {}
    for k, v in raw.items():
        out[int(k)] = float(v)
    return out


def _ensure_all_joints(pose: Dict[int, float]) -> Dict[int, float]:
    for jid in JointController.JOINT_MAP:
        if jid not in pose:
            pose[jid] = 0.0
    return pose


class ArmsOnWaist:
    """Последовательность: ноги по очереди (слева, справа) → руки вместе → талия."""

    def __init__(self):
        print("[SAI Action] Инициализация (поза из Pose Studio)...")
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
        """Один сустав за раз; завершённые — в locked; остальные — из fixed_rad."""
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
        """Синхронное движение для всех joint_ids; прочие суставы — текущие fixed_rad."""
        targets_rad: Dict[int, float] = {}
        for jid in joint_ids:
            q_req = deg2rad(targets_deg[jid])
            targets_rad[jid] = clamp_q(jid, q_req)

        start: Dict[int, float] = {jid: fixed_rad[jid] for jid in joint_ids}
        max_vel = min(get_limit(jid)["max_vel"] for jid in joint_ids)
        safe_speed = min(max_vel, speed)
        distances = [abs(targets_rad[jid] - start[jid]) for jid in joint_ids]
        max_dist = max(distances) if distances else 0.0
        duration = max_dist / safe_speed if safe_speed > 0 else 0.1
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

    def execute(self, speed: float = 0.5) -> None:
        targets_deg = _ensure_all_joints(_load_pose_deg())
        if all(abs(v) < 1e-6 for v in targets_deg.values()):
            print(
                "[SAI Action] Внимание: все углы в POSE_DEG / json ≈ 0. "
                "Подставьте данные из Pose Studio (Save Pose)."
            )

        fixed_rad = self._snapshot_rad()
        locked: Set[int] = set()

        print("[SAI Action] Фаза 1: левая нога по суставам…")
        self._sequential_leg_joints(LEFT_LEG, targets_deg, speed, fixed_rad, locked)

        print("[SAI Action] Фаза 2: правая нога по суставам…")
        self._sequential_leg_joints(RIGHT_LEG, targets_deg, speed, fixed_rad, locked)

        print("[SAI Action] Фаза 3: обе руки параллельно…")
        self._smooth_parallel(ARMS, targets_deg, speed, fixed_rad)

        print("[SAI Action] Фаза 4: талия (последней)…")
        self._smooth_parallel(WAIST, targets_deg, speed, fixed_rad)

        print("\n[SAI SUCCESS] Поза достигнута. Удержание + Ctrl+C для выхода.")
        try:
            while True:
                for jid in JointController.JOINT_MAP:
                    self.ctrl.set_joint_deg(jid, targets_deg[jid])
                self.ctrl.publish()
                time.sleep(0.01)
        except KeyboardInterrupt:
            print("\n[SAI Action] Остановлено пользователем.")


if __name__ == "__main__":
    action = ArmsOnWaist()
    action.execute()
