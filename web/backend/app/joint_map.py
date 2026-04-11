"""G1 29-DoF joint map (mirrors core_control.joint_controller.Joint_MAP)."""

JOINT_MAP: dict[int, str] = {
    0: "left_hip_pitch",
    1: "left_hip_roll",
    2: "left_hip_yaw",
    3: "left_knee",
    4: "left_ankle_pitch",
    5: "left_ankle_roll",
    6: "right_hip_pitch",
    7: "right_hip_roll",
    8: "right_hip_yaw",
    9: "right_knee",
    10: "right_ankle_pitch",
    11: "right_ankle_roll",
    12: "waist_yaw",
    13: "waist_roll",
    14: "waist_pitch",
    15: "left_shoulder_pitch",
    16: "left_shoulder_roll",
    17: "left_shoulder_yaw",
    18: "left_elbow",
    19: "left_wrist_roll",
    20: "left_wrist_pitch",
    21: "left_wrist_yaw",
    22: "right_shoulder_pitch",
    23: "right_shoulder_roll",
    24: "right_shoulder_yaw",
    25: "right_elbow",
    26: "right_wrist_roll",
    27: "right_wrist_pitch",
    28: "right_wrist_yaw",
}

# Pose Studio groups (indices)
GROUPS: list[tuple[str, list[int]]] = [
    ("Левая рука", list(range(15, 22))),
    ("Правая рука", list(range(22, 29))),
    ("Торс", list(range(12, 15))),
    ("Левая нога", list(range(0, 6))),
    ("Правая нога", list(range(6, 12))),
]

EST_SEC_PER_KEYFRAME = 8.0
