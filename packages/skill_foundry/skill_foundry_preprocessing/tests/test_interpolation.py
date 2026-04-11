import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

TEST_FILE = Path(__file__).resolve()
SDK_PYTHON_ROOT = TEST_FILE.parents[2]
if str(SDK_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_PYTHON_ROOT))

from core_control.config.joint_limits import JOINT_LIMITS, clamp_q  # noqa: E402
from skill_foundry_phase0.contract_validator import validate_phase0_directory  # noqa: E402
from skill_foundry_preprocessing.interpolation import (  # noqa: E402
    keyframes_to_reference_trajectory,
)


def _deg2rad(d: float) -> float:
    return float(np.deg2rad(d))


class TestInterpolation(unittest.TestCase):
    def test_linear_trend_three_points_matches_spline_midpoint(self) -> None:
        """Три точки по суставу 0: линейный тренд; середина близка к линейной."""
        kf = {
            "schema_version": "1.0.0",
            "units": {"angle": "degrees", "time": "seconds"},
            "keyframes": [
                {"timestamp_s": 0.0, "joints_deg": {"0": 0.0}},
                {"timestamp_s": 1.0, "joints_deg": {"0": 30.0}},
                {"timestamp_s": 2.0, "joints_deg": {"0": 60.0}},
            ],
        }
        ref = keyframes_to_reference_trajectory(kf, frequency_hz=2.0, joint_order=["0"])
        # t_end=2, hz=2 -> floor(4)+1 = 5 samples at 0, 0.5, 1.0, 1.5, 2.0
        pos = ref["joint_positions"]
        self.assertEqual(len(pos), 5)
        # t=1.0 should be 30 deg = pi/6 rad
        self.assertAlmostEqual(pos[2][0], _deg2rad(30.0), places=5)

    def test_non_monotonic_timestamps_raise(self) -> None:
        kf = {
            "schema_version": "1.0.0",
            "units": {"angle": "degrees", "time": "seconds"},
            "keyframes": [
                {"timestamp_s": 0.0, "joints_deg": {"0": 0.0}},
                {"timestamp_s": 1.0, "joints_deg": {"0": 1.0}},
                {"timestamp_s": 1.0, "joints_deg": {"0": 2.0}},
            ],
        }
        with self.assertRaises(ValueError):
            keyframes_to_reference_trajectory(kf, frequency_hz=50.0, joint_order=["0"])

    def test_aggressive_keyframes_clipped_to_limits(self) -> None:
        """Резкий зигзаг по keyframes может давать вылеты сплайна; позиции после clamp в лимитах."""
        kf = {
            "schema_version": "1.0.0",
            "units": {"angle": "degrees", "time": "seconds"},
            "keyframes": [
                {"timestamp_s": 0.0, "joints_deg": {"5": 0.0}},
                {"timestamp_s": 0.1, "joints_deg": {"5": 45.0}},
                {"timestamp_s": 0.2, "joints_deg": {"5": -45.0}},
                {"timestamp_s": 0.3, "joints_deg": {"5": 0.0}},
            ],
        }
        ref = keyframes_to_reference_trajectory(kf, frequency_hz=200.0, joint_order=["5"])
        lim = JOINT_LIMITS[5]
        for row in ref["joint_positions"]:
            self.assertGreaterEqual(row[0], lim["min"] - 1e-5)
            self.assertLessEqual(row[0], lim["max"] + 1e-5)

    def test_clipping_out_of_range(self) -> None:
        lim = JOINT_LIMITS[0]
        # Задать угол сильно выше max в градусах
        huge_deg = float(np.rad2deg(lim["max"]) + 90.0)
        kf = {
            "schema_version": "1.0.0",
            "units": {"angle": "degrees", "time": "seconds"},
            "keyframes": [
                {"timestamp_s": 0.0, "joints_deg": {"0": 0.0}},
                {"timestamp_s": 1.0, "joints_deg": {"0": huge_deg}},
            ],
        }
        ref = keyframes_to_reference_trajectory(kf, frequency_hz=10.0, joint_order=["0"])
        for row in ref["joint_positions"]:
            self.assertLessEqual(row[0], lim["max"] + 1e-6)
            self.assertGreaterEqual(row[0], lim["min"] - 1e-6)

    def test_single_keyframe_constant(self) -> None:
        kf = {
            "schema_version": "1.0.0",
            "units": {"angle": "degrees", "time": "seconds"},
            "keyframes": [
                {"timestamp_s": 0.5, "joints_deg": {"1": 10.0}},
            ],
        }
        ref = keyframes_to_reference_trajectory(kf, frequency_hz=20.0, joint_order=["1"])
        q = _deg2rad(10.0)
        for row in ref["joint_positions"]:
            self.assertAlmostEqual(row[0], clamp_q(1, q), places=6)

    def test_two_keyframes_linear(self) -> None:
        kf = {
            "schema_version": "1.0.0",
            "units": {"angle": "degrees", "time": "seconds"},
            "keyframes": [
                {"timestamp_s": 0.0, "joints_deg": {"2": 0.0}},
                {"timestamp_s": 2.0, "joints_deg": {"2": 0.0}},
            ],
        }
        ref = keyframes_to_reference_trajectory(kf, frequency_hz=2.0, joint_order=["2"])
        # t = 0, 0.5, 1, 1.5, 2 -> all zero
        self.assertEqual(len(ref["joint_positions"]), 5)
        for row in ref["joint_positions"]:
            self.assertAlmostEqual(row[0], 0.0, places=6)

    def test_forward_fill_missing_joint_in_frame(self) -> None:
        kf = {
            "schema_version": "1.0.0",
            "units": {"angle": "degrees", "time": "seconds"},
            "keyframes": [
                {"timestamp_s": 0.0, "joints_deg": {"3": 5.0, "4": 1.0}},
                {"timestamp_s": 1.0, "joints_deg": {"3": 15.0}},
            ],
        }
        ref = keyframes_to_reference_trajectory(kf, frequency_hz=1.0, joint_order=["3", "4"])
        # At t=1, joint 4 forward-filled to 1.0 deg
        last = ref["joint_positions"][-1]
        self.assertAlmostEqual(last[1], _deg2rad(1.0), places=5)

    def test_joint_velocities_present_by_default(self) -> None:
        kf = {
            "schema_version": "1.0.0",
            "units": {"angle": "degrees", "time": "seconds"},
            "keyframes": [
                {"timestamp_s": 0.0, "joints_deg": {"0": 0.0}},
                {"timestamp_s": 1.0, "joints_deg": {"0": 0.0}},
            ],
        }
        ref = keyframes_to_reference_trajectory(kf, frequency_hz=10.0, joint_order=["0"])
        self.assertIn("joint_velocities", ref)
        self.assertEqual(len(ref["joint_velocities"]), len(ref["joint_positions"]))

    def test_omit_velocities_flag(self) -> None:
        kf = {
            "schema_version": "1.0.0",
            "units": {"angle": "degrees", "time": "seconds"},
            "keyframes": [
                {"timestamp_s": 0.0, "joints_deg": {"0": 0.0}},
                {"timestamp_s": 1.0, "joints_deg": {"0": 0.0}},
            ],
        }
        ref = keyframes_to_reference_trajectory(
            kf, frequency_hz=10.0, joint_order=["0"], include_joint_velocities=False
        )
        self.assertNotIn("joint_velocities", ref)

    def test_validate_phase0_with_generated_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keyframes_payload = {
                "schema_version": "1.0.0",
                "units": {"angle": "degrees", "time": "seconds"},
                "robot_model": "g1_29dof",
                "keyframes": [
                    {"timestamp_s": 0.0, "joints_deg": {str(i): 0.0 for i in range(29)}},
                    {"timestamp_s": 0.5, "joints_deg": {str(i): 0.0 for i in range(29)}},
                    {"timestamp_s": 1.0, "joints_deg": {str(i): 0.0 for i in range(29)}},
                ],
            }
            (root / "keyframes.json").write_text(
                json.dumps(keyframes_payload, indent=2), encoding="utf-8"
            )
            order = [str(i) for i in range(29)]
            ref = keyframes_to_reference_trajectory(keyframes_payload, frequency_hz=50.0, joint_order=order)
            (root / "reference_trajectory.json").write_text(json.dumps(ref, indent=2), encoding="utf-8")
            # minimal motion/scenario/demo so directory validation can run if needed
            (root / "motion.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "motion_id": "m1",
                        "source_keyframes_id": "kf1",
                        "keyframe_timestamps_s": [0.0, 0.5, 1.0],
                    }
                ),
                encoding="utf-8",
            )
            (root / "scenario.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "scenario_id": "s1",
                        "steps": [
                            {
                                "motion_id": "m1",
                                "transition": {"type": "on_complete"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "demonstration_dataset.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "robot_model": "g1_29dof",
                        "sampling_hz": 50.0,
                        "obs_schema_ref": "obs_v1",
                        "episodes": [
                            {
                                "episode_id": "ep1",
                                "steps": [
                                    {
                                        "obs": [0.0],
                                        "act": [0.0],
                                        "done": False,
                                    },
                                    {
                                        "obs": [0.0],
                                        "act": [0.0],
                                        "done": True,
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = validate_phase0_directory(root)
            self.assertEqual(result["status"], "ok", msg=str(result.get("errors")))


if __name__ == "__main__":
    unittest.main()
