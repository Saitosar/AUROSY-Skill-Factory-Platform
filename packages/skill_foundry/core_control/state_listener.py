import time
from typing import Dict, Optional

from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_


class StateListener:
    """Универсальный блок сбора всей телеметрии робота."""
    def __init__(self):
        self.sub = ChannelSubscriber("rt/lowstate", LowState_)
        self.sub.Init(self.state_callback)
        self.low_state = None

    def state_callback(self, msg):
        self.low_state = msg

    def wait_for_ready(self):
        print("[SAI Listener] Установка связи с телеметрией...", end="\r")
        while self.low_state is None:
            time.sleep(0.1)
        print("[SAI Listener] Телеметрия активна. Все системы в норме.")

    def get_joint_pos(self, joint_id):
        return self.low_state.motor_state[joint_id].q if self.low_state else None

    def get_imu(self):
        return self.low_state.imu_state if self.low_state else None

    def dump_joint_positions(
        self,
        joint_names: Optional[Dict[int, str]] = None,
        n: int = 29,
    ) -> None:
        """
        Печать motor_state[0..n-1].q из последнего LowState (радианы).
        joint_names — например JointController.JOINT_MAP для подписей.
        """
        if not self.low_state:
            print("[SAI Listener] dump_joint_positions: low_state отсутствует")
            return
        print("[SAI Listener] Начальное состояние суставов (rt/lowstate → motor_state[i].q, рад):")
        for i in range(n):
            q = self.low_state.motor_state[i].q
            if joint_names and i in joint_names:
                name = joint_names[i]
            else:
                name = f"motor_{i}"
            print(f"  {i:2d}  {name:24s}  q = {q:+.4f}")
        print(f"[SAI Listener] Показано моторов: {n} (индексы 0–{n - 1}).")
