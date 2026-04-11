import time
import math
import sys
import os

# Автоматическое добавление путей для SAI Platform
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path: sys.path.append(root_dir)

from core_control.joint_controller import JointController
from core_control.state_listener import StateListener
from core_control.config.joint_limits import clamp_q, get_limit
from core_control.utils.conversions import deg2rad

class AtomicMove:
    """Универсальный безопасный контроллер суставов."""
    def __init__(self, print_initial_state: bool = True):
        self.ctrl = JointController()
        self.listener = StateListener()
        self.listener.wait_for_ready()
        if print_initial_state:
            self.listener.dump_joint_positions(JointController.JOINT_MAP, n=29)

    def safe_move(self, joint_id, target_q, speed=0.5):
        limits = get_limit(joint_id)
        requested_q = target_q
        target_q = clamp_q(joint_id, target_q)
        if abs(target_q - requested_q) > 1e-4:
            print(
                f"[SAI Atomic] Предупреждение: сустав {joint_id} ({limits['name']}): "
                f"запрошено {requested_q:.4f} рад, применено {target_q:.4f} (лимит g1_29dof)"
            )
        safe_speed = min(limits['max_vel'], speed)
        
        start_q = self.listener.get_joint_pos(joint_id)
        if start_q is None: return

        distance = abs(target_q - start_q)
        duration = distance / safe_speed if safe_speed > 0 else 0.1
        
        print(f"[SAI Atomic] Движение сустава {joint_id} ({limits['name']})")
        print(f"Старт: {start_q:.2f} | Цель: {target_q:.2f} | Время: {duration:.2f}s")

        steps = int(duration / 0.005)
        for i in range(steps + 1):
            t = i / steps if steps > 0 else 1.0
            smooth_t = (1.0 - math.cos(t * math.pi)) / 2.0
            current_target = start_q + (target_q - start_q) * smooth_t
            
            self.ctrl.set_joint(joint_id, current_target)
            self.ctrl.publish()
            time.sleep(0.005)

        print("[SAI Atomic] Движение завершено.")

    def safe_move_deg(self, joint_id, target_deg, speed=0.5):
        """То же safe_move, но цель задается в градусах."""
        self.safe_move(joint_id, deg2rad(target_deg), speed=speed)

if __name__ == "__main__":
    node = AtomicMove()
    # Тестовый подъем левой руки (15) на 45 градусов (0.78 рад)
    node.safe_move(joint_id=15, target_q=0.78, speed=0.4)