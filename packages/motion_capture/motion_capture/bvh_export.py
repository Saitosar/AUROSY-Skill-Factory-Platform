"""BVH format export for recorded motion capture sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np


@dataclass
class RecordingSession:
    """Accumulates pose frames during a recording session."""

    fps: float = 30.0
    frames: List[Tuple[np.ndarray, float]] = field(default_factory=list)

    def add_frame(self, landmarks: np.ndarray, timestamp_ms: float) -> None:
        self.frames.append((landmarks.copy(), timestamp_ms))

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def duration_sec(self) -> float:
        if len(self.frames) < 2:
            return 0.0
        return (self.frames[-1][1] - self.frames[0][1]) / 1000.0

    def clear(self) -> None:
        self.frames.clear()


MEDIAPIPE_SKELETON = {
    "Hips": 23,
    "Spine": 11,
    "Neck": 0,
    "Head": 0,
    "LeftShoulder": 11,
    "LeftArm": 13,
    "LeftForeArm": 15,
    "LeftHand": 17,
    "RightShoulder": 12,
    "RightArm": 14,
    "RightForeArm": 16,
    "RightHand": 18,
    "LeftUpLeg": 23,
    "LeftLeg": 25,
    "LeftFoot": 27,
    "RightUpLeg": 24,
    "RightLeg": 26,
    "RightFoot": 28,
}


class BVHExporter:
    """Export RecordingSession to BVH format."""

    def __init__(self, scale: float = 100.0):
        self.scale = scale

    def export(self, session: RecordingSession) -> str:
        lines: List[str] = []
        lines.append("HIERARCHY")
        lines.append("ROOT Hips")
        lines.append("{")
        lines.append("  OFFSET 0.0 0.0 0.0")
        lines.append("  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation")
        self._add_joint(lines, "Spine", 1)
        self._add_joint(lines, "LeftUpLeg", 1)
        self._add_joint(lines, "RightUpLeg", 1)
        lines.append("}")

        lines.append("MOTION")
        lines.append(f"Frames: {session.frame_count}")
        frame_time = 1.0 / session.fps if session.fps > 0 else 0.033
        lines.append(f"Frame Time: {frame_time:.6f}")

        for landmarks, _ in session.frames:
            frame_data = self._landmarks_to_frame_data(landmarks)
            lines.append(" ".join(f"{value:.4f}" for value in frame_data))

        return "\n".join(lines)

    def _add_joint(self, lines: List[str], name: str, indent: int) -> None:
        prefix = "  " * indent
        lines.extend(
            [
                f"{prefix}JOINT {name}",
                f"{prefix}{{",
                f"{prefix}  OFFSET 0.0 10.0 0.0",
                f"{prefix}  CHANNELS 3 Zrotation Xrotation Yrotation",
                f"{prefix}  End Site",
                f"{prefix}  {{",
                f"{prefix}    OFFSET 0.0 10.0 0.0",
                f"{prefix}  }}",
                f"{prefix}}}",
            ]
        )

    def _landmarks_to_frame_data(self, landmarks: np.ndarray) -> List[float]:
        if landmarks.shape[0] <= MEDIAPIPE_SKELETON["Hips"]:
            return [0.0] * 15
        hip_idx = MEDIAPIPE_SKELETON["Hips"]
        root_pos = landmarks[hip_idx] * self.scale
        return [
            float(root_pos[0]),
            float(root_pos[1]),
            float(root_pos[2]),
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ]

