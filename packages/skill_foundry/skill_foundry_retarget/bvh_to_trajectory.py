"""Convert BVH clips into approximate landmarks/reference trajectories."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import numpy as np

from .joint_map import G1_JOINT_ORDER

_MOTION_RE = re.compile(r"MOTION\s*\n", flags=re.IGNORECASE)
_DEFAULT_ROOT_SCALE = 100.0


class BVHConversionError(ValueError):
    """Raised when BVH payload does not match expected minimal format."""


@dataclass(frozen=True)
class ParsedBvhMotion:
    """Parsed MOTION section values."""

    frame_time: float
    frames: np.ndarray

    @property
    def frame_count(self) -> int:
        return int(self.frames.shape[0])

    @property
    def channel_count(self) -> int:
        return int(self.frames.shape[1]) if self.frames.ndim == 2 else 0


class BVHToTrajectoryConverter:
    """Convert BVH text into lossy but pipeline-compatible data."""

    def __init__(self, *, root_scale: float = _DEFAULT_ROOT_SCALE):
        self.root_scale = root_scale

    def parse(self, bvh_content: str) -> ParsedBvhMotion:
        marker = _MOTION_RE.search(bvh_content)
        if marker is None:
            raise BVHConversionError("BVH does not contain MOTION section")
        lines = [ln.strip() for ln in bvh_content[marker.end() :].splitlines() if ln.strip()]
        frame_time = 0.033
        expected_frames: int | None = None
        rows: list[list[float]] = []
        for line in lines:
            if line.lower().startswith("frames:"):
                expected_frames = int(line.split(":", 1)[1].strip())
                continue
            if line.lower().startswith("frame time:"):
                frame_time = float(line.split(":", 1)[1].strip())
                continue
            parts = line.split()
            if not parts:
                continue
            rows.append([float(v) for v in parts])

        if not rows:
            raise BVHConversionError("BVH MOTION section contains no frames")

        channel_count = len(rows[0])
        if channel_count < 6:
            raise BVHConversionError("BVH frame must contain at least 6 root channels")
        if any(len(r) != channel_count for r in rows):
            raise BVHConversionError("BVH frames must have the same channel count")
        if expected_frames is not None and expected_frames != len(rows):
            raise BVHConversionError("BVH Frames header does not match frame rows")

        return ParsedBvhMotion(frame_time=frame_time, frames=np.asarray(rows, dtype=np.float32))

    def to_landmarks_approx(self, motion: ParsedBvhMotion) -> np.ndarray:
        """Build a synthetic [N,33,3] landmarks sequence from root translations."""
        landmarks = np.zeros((motion.frame_count, 33, 3), dtype=np.float32)
        for idx, frame in enumerate(motion.frames):
            root = frame[:3] / float(self.root_scale)
            pose = np.repeat(root[np.newaxis, :], 33, axis=0)

            # Keep a stable humanoid skeleton around root so retargeting math remains finite.
            pose[23] = root + np.array([-0.08, -0.05, 0.0], dtype=np.float32)  # left hip
            pose[24] = root + np.array([0.08, -0.05, 0.0], dtype=np.float32)  # right hip
            pose[25] = root + np.array([-0.08, -0.45, 0.02], dtype=np.float32)  # left knee
            pose[26] = root + np.array([0.08, -0.45, 0.02], dtype=np.float32)  # right knee
            pose[27] = root + np.array([-0.1, -0.86, 0.06], dtype=np.float32)  # left ankle
            pose[28] = root + np.array([0.1, -0.86, 0.06], dtype=np.float32)  # right ankle
            pose[11] = root + np.array([-0.14, 0.36, 0.0], dtype=np.float32)  # left shoulder
            pose[12] = root + np.array([0.14, 0.36, 0.0], dtype=np.float32)  # right shoulder
            pose[13] = root + np.array([-0.32, 0.21, 0.0], dtype=np.float32)  # left elbow
            pose[14] = root + np.array([0.32, 0.21, 0.0], dtype=np.float32)  # right elbow
            pose[15] = root + np.array([-0.45, 0.07, 0.0], dtype=np.float32)  # left wrist
            pose[16] = root + np.array([0.45, 0.07, 0.0], dtype=np.float32)  # right wrist
            pose[0] = root + np.array([0.0, 0.55, 0.02], dtype=np.float32)  # nose/head anchor

            landmarks[idx] = pose
        return landmarks

    def convert(self, bvh_content: str) -> dict[str, Any]:
        """Return a compact trajectory contract for diagnostics/tests."""
        motion = self.parse(bvh_content)
        return {
            "version": "1.0",
            "robot": "unitree_g1_29dof",
            "joint_order": list(G1_JOINT_ORDER),
            "dt": motion.frame_time,
            "frames": [{"joint_angles_rad": [0.0] * len(G1_JOINT_ORDER)} for _ in range(motion.frame_count)],
            "source": "bvh_motion_capture_lossy",
            "warnings": [
                "BVH conversion is lossy: only root translation is preserved in current exporter."
            ],
        }
