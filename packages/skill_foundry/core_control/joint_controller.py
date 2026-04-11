from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
from unitree_sdk2py.utils.crc import CRC

from core_control.config.joint_limits import clamp_q
from core_control.utils.conversions import deg2rad

class JointController:
    """
    HAL (Hardware Abstraction Layer) для G1.
    Отвечает за передачу низкоуровневых команд и хранение карты суставов.
    """
    
    # Подробная карта актуаторов G1 (Ориентация: рука вперед, ладонь вниз)
    JOINT_MAP = {
        # ЛЕВАЯ НОГА
        0:  "left_hip_pitch",       # Бедро: Вперед / Назад
        1:  "left_hip_roll",        # Бедро: Вбок (отведение) / К центру
        2:  "left_hip_yaw",         # Бедро: Вращение (носок внутрь / наружу)
        3:  "left_knee",            # Колено: Сгибание / Разгибание
        4:  "left_ankle_pitch",     # Лодыжка: Носок вверх / вниз
        5:  "left_ankle_roll",      # Лодыжка: Наклон стопы влево / вправо
        
        # ПРАВАЯ НОГА
        6:  "right_hip_pitch",      # Бедро: Вперед / Назад
        7:  "right_hip_roll",       # Бедро: Вбок (отведение) / К центру
        8:  "right_hip_yaw",        # Бедро: Вращение (носок внутрь / наружу)
        9:  "right_knee",           # Колено: Сгибание / Разгибание
        10: "right_ankle_pitch",    # Лодыжка: Носок вверх / вниз
        11: "right_ankle_roll",     # Лодыжка: Наклон стопы влево / вправо
        
        # КОРПУС (ТАЛИЯ)
        12: "waist_yaw",            # Поворот корпуса влево / вправо
        13: "waist_roll",           # Наклон корпуса вбок (лево / право)
        14: "waist_pitch",          # Наклон корпуса вперед (поклон) / назад
        
        # ЛЕВАЯ РУКА
        15: "left_shoulder_pitch",  # Плечо: Вперед / Назад
        16: "left_shoulder_roll",   # Плечо: Вбок (подъем) / Вниз (к телу)
        17: "left_shoulder_yaw",    # Плечо: Вращение руки вокруг своей оси
        18: "left_elbow",           # Локоть: Сгибание / Разгибание
        19: "left_wrist_roll",      # Запястье: Вращение (ладонь вверх / вниз)
        20: "left_wrist_pitch",     # Кисть: Вправо / Влево (горизонтально)
        21: "left_wrist_yaw",       # Кисть: Вверх / Вниз (вертикально)
        
        # ПРАВАЯ РУКА
        22: "right_shoulder_pitch", # Плечо: Вперед / Назад
        23: "right_shoulder_roll",  # Плечо: Вбок (подъем) / Вниз (к телу)
        24: "right_shoulder_yaw",   # Плечо: Вращение руки вокруг своей оси
        25: "right_elbow",          # Локоть: Сгибание / Разгибание
        26: "right_wrist_roll",     # Запястье: Вращение (ладонь вверх / вниз)
        27: "right_wrist_pitch",    # Кисть: Вправо / Влево (горизонтально)
        28: "right_wrist_yaw"       # Кисть: Вверх / Вниз (вертикально)
    }

    def __init__(self, domain_id=1, interface="lo0"):
        ChannelFactoryInitialize(domain_id, interface)
        self.pub = ChannelPublisher("rt/lowcmd", LowCmd_)
        self.pub.Init()
        self.crc = CRC()
        self.cmd = unitree_hg_msg_dds__LowCmd_()
        
        # Инициализируем ВСЕ 35 моторов в пассивном режиме; tau — поле для моста MuJoCo / железа
        for i in range(35):
            self.cmd.motor_cmd[i].mode = 0x00
            self.cmd.motor_cmd[i].q = 0.0
            self.cmd.motor_cmd[i].dq = 0.0
            self.cmd.motor_cmd[i].tau = 0.0
            self.cmd.motor_cmd[i].kp = 0.0
            self.cmd.motor_cmd[i].kd = 0.0

    def set_joint(self, joint_id, q, kp=30.0, kd=2.0):
        """Подготавливает команду для сустава; q ограничивается лимитами g1_29dof (joint_limits)."""
        q = clamp_q(joint_id, q)
        self.cmd.motor_cmd[joint_id].mode = 0x01
        self.cmd.motor_cmd[joint_id].q = q
        self.cmd.motor_cmd[joint_id].dq = 0.0
        self.cmd.motor_cmd[joint_id].tau = 0.0
        self.cmd.motor_cmd[joint_id].kp = kp
        self.cmd.motor_cmd[joint_id].kd = kd

    def set_joint_deg(self, joint_id, degrees, kp=30.0, kd=2.0):
        """
        Удобный API для задания цели в градусах.
        Пример: set_joint_deg(16, 30) эквивалентно set_joint(16, deg2rad(30)).
        """
        self.set_joint(joint_id, deg2rad(degrees), kp=kp, kd=kd)

    def set_motor_passive(self, joint_id: int) -> None:
        """Режим без PD: как при старте HAL (MuJoCo / железо не держит цель)."""
        m = self.cmd.motor_cmd[joint_id]
        m.mode = 0x00
        m.q = 0.0
        m.dq = 0.0
        m.tau = 0.0
        m.kp = 0.0
        m.kd = 0.0

    def set_all_motors_passive(self, num_motors: int = 35) -> None:
        """Все слоты LowCmd в пассив (0..num_motors-1)."""
        for i in range(num_motors):
            self.set_motor_passive(i)

    def publish(self):
        """Отправляет накопленные команды в симулятор."""
        self.cmd.crc = self.crc.Crc(self.cmd)
        self.pub.Write(self.cmd)