#!/usr/bin/env python3
"""
Прямой тест JointController без AtomicMove:
мотор 16 (left_shoulder_roll), запрос q = 2.5 рад.
Внутри set_joint сработает clamp_q → на шине будет ≤ max из joint_limits.

Запуск (MuJoCo с мостом уже должен слушать rt/lowcmd):
  cd .../mid_level_motions/basic_actions
  python3 test_joint_controller_motor16.py
"""
import os
import sys
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core_control.config.joint_limits import clamp_q
from core_control.joint_controller import JointController
from core_control.state_listener import StateListener


def main():
    joint_id = 16
    q_req = 2.5
    q_eff = clamp_q(joint_id, q_req)

    print(f"[test_joint_controller] joint_id={joint_id} ({JointController.JOINT_MAP[joint_id]})")
    print(f"[test_joint_controller] запрошено q={q_req} рад → после clamp: {q_eff:.4f} рад")
    print("[test_joint_controller] удержание ~8 с @ 200 Гц (только этот мотор в команде)")
    print("[test_joint_controller] печатаем cmd/state каждые 0.1 с для сверки с UI")

    ctrl = JointController()
    listener = StateListener()
    listener.wait_for_ready()
    ctrl.set_joint(joint_id, q_req)
    print(f"[test_joint_controller] motor_cmd[{joint_id}].q сразу после set_joint = {ctrl.cmd.motor_cmd[joint_id].q:.4f}")

    t0 = time.time()
    t_end = t0 + 8.0
    next_print = t0
    while time.time() < t_end:
        ctrl.set_joint(joint_id, q_req)
        ctrl.publish()
        now = time.time()
        if now >= next_print:
            cmd_q = ctrl.cmd.motor_cmd[joint_id].q
            state_q = listener.get_joint_pos(joint_id)
            state_s = "None" if state_q is None else f"{state_q:+.4f}"
            print(f"[t={now - t0:5.2f}s] cmd[{joint_id}]={cmd_q:+.4f} | state[{joint_id}]={state_s}")
            next_print += 0.1
        time.sleep(0.005)

    print("[test_joint_controller] завершено.")


if __name__ == "__main__":
    main()
