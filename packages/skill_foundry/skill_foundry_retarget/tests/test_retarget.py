from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

TEST_FILE = Path(__file__).resolve()
SDK_PYTHON_ROOT = TEST_FILE.parents[2]
if str(SDK_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_PYTHON_ROOT))

from skill_foundry_retarget import Retargeter


def _synthetic_landmarks() -> np.ndarray:
    landmarks = np.zeros((33, 3), dtype=np.float32)
    for idx in range(33):
        landmarks[idx] = np.array([idx * 0.01, idx * 0.015, idx * 0.02], dtype=np.float32)
    return landmarks


class TestRetargeter(unittest.TestCase):
    def test_compute_returns_29_joint_angles(self) -> None:
        retargeter = Retargeter()
        frame = _synthetic_landmarks()
        result = retargeter.compute(frame)
        self.assertEqual(result.joint_angles_rad.shape, (29,))
        self.assertTrue(np.all(np.isfinite(result.joint_angles_rad)))

    def test_compute_batch_keeps_frame_count(self) -> None:
        retargeter = Retargeter()
        frame = _synthetic_landmarks()
        batch = np.stack([frame, frame * 1.05], axis=0)
        out, warnings = retargeter.compute_batch(batch)
        self.assertEqual(out.shape, (2, 29))
        self.assertIsInstance(warnings, list)

    def test_invalid_shape_raises(self) -> None:
        retargeter = Retargeter()
        with self.assertRaises(ValueError):
            retargeter.compute(np.zeros((32, 3), dtype=np.float32))


if __name__ == "__main__":
    unittest.main()
