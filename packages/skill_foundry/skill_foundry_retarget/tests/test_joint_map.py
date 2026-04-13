from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
SDK_PYTHON_ROOT = TEST_FILE.parents[2]
if str(SDK_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_PYTHON_ROOT))

from skill_foundry_retarget.joint_map import G1_JOINT_ORDER, load_joint_map


class TestJointMap(unittest.TestCase):
    def test_load_default_joint_map_contains_all_g1_joints(self) -> None:
        jm = load_joint_map()
        self.assertEqual(jm.source_skeleton, "mediapipe_pose_33")
        self.assertEqual(jm.target_robot, "unitree_g1_29dof")
        self.assertEqual(set(jm.mappings.keys()), set(G1_JOINT_ORDER))

    def test_missing_joint_fails_validation(self) -> None:
        payload = {
            "version": "1.0",
            "source_skeleton": "mediapipe_pose_33",
            "target_robot": "unitree_g1_29dof",
            "mappings": {
                "left_hip_pitch": {
                    "source_landmarks": [11, 23, 25],
                    "computation": "angle_3points",
                    "limits": [-1.0, 1.0],
                }
            },
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "joint_map.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_joint_map(path)


if __name__ == "__main__":
    unittest.main()
