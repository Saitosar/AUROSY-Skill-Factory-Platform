#!/usr/bin/env python3
"""
Проверка: один мотор через AtomicMove → сравнение цифры в UI MuJoCo с логом.

По умолчанию: DDS индекс 16 = left_shoulder_roll, цель 2.5 рад (фактическая цель
после clamp — см. вывод [SAI Atomic]).

Запуск (из каталога basic_actions):
  python3 test_single_motor.py
  python3 test_single_motor.py --target 1.5
  python3 test_single_motor.py --joint 16 --target 2.5 --speed 0.3
"""
import argparse
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core_control.low_level_motions.atomic_move import AtomicMove


def main():
    p = argparse.ArgumentParser(description="Один сустав: safe_move + только выбранный joint_id")
    p.add_argument("--joint", type=int, default=16, help="Индекс motor_cmd / LowCmd (по умолчанию 16 = left_shoulder_roll)")
    p.add_argument("--target", type=float, default=2.5, help="Запрошенный угол, рад")
    p.add_argument("--speed", type=float, default=0.4, help="Скорость движения для safe_move")
    args = p.parse_args()

    print(
        f"[test_single_motor] joint_id={args.joint} requested_target={args.target} rad | "
        "сравни число в UI с «Цель» после clamp в логе AtomicMove"
    )
    node = AtomicMove(print_initial_state=False)
    node.safe_move(args.joint, args.target, speed=args.speed)


if __name__ == "__main__":
    main()
