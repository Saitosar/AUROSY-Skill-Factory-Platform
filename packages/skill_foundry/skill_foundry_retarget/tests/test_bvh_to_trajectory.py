from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

TEST_FILE = Path(__file__).resolve()
SDK_PYTHON_ROOT = TEST_FILE.parents[2]
if str(SDK_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_PYTHON_ROOT))

from skill_foundry_retarget.bvh_to_trajectory import BVHConversionError, BVHToTrajectoryConverter


def _sample_bvh() -> str:
    return """HIERARCHY
ROOT Hips
{
  OFFSET 0.0 0.0 0.0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  End Site
  {
    OFFSET 0.0 10.0 0.0
  }
}
MOTION
Frames: 2
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0
1.0 0.0 0.0 0.0 0.0 0.0
"""


def test_converter_produces_reference_trajectory() -> None:
    converter = BVHToTrajectoryConverter()
    trajectory = converter.convert(_sample_bvh())
    assert "joint_order" in trajectory
    assert "frames" in trajectory
    assert "dt" in trajectory
    assert len(trajectory["frames"]) == 2
    assert trajectory["warnings"]


def test_parse_and_landmarks_shape() -> None:
    converter = BVHToTrajectoryConverter()
    motion = converter.parse(_sample_bvh())
    landmarks = converter.to_landmarks_approx(motion)
    assert landmarks.shape == (2, 33, 3)
    assert np.all(np.isfinite(landmarks))


def test_parse_fails_without_motion() -> None:
    converter = BVHToTrajectoryConverter()
    with pytest.raises(BVHConversionError):
        converter.parse("HIERARCHY\nROOT Hips\n{}")
