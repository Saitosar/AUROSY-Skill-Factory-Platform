import json
import sys
import tempfile
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
SDK_PYTHON_ROOT = TEST_FILE.parents[2]
if str(SDK_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_PYTHON_ROOT))

from skill_foundry_phase0.contract_validator import validate_phase0_directory


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestPhase0ContractValidator(unittest.TestCase):
    def test_valid_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_json(
                root / "keyframes.json",
                {
                    "schema_version": "1.0.0",
                    "units": {"angle": "degrees", "time": "seconds"},
                    "robot_model": "g1_29dof",
                    "keyframes": [
                        {"timestamp_s": 0.0, "joints_deg": {"0": 0.0, "1": 1.0}},
                        {"timestamp_s": 1.0, "joints_deg": {"0": 2.0, "1": -1.0}},
                    ],
                },
            )
            _write_json(
                root / "motion.json",
                {
                    "schema_version": "1.0.0",
                    "motion_id": "wave_v1",
                    "source_keyframes_id": "kf_demo",
                    "keyframe_timestamps_s": [0.0, 1.0],
                },
            )
            _write_json(
                root / "scenario.json",
                {
                    "schema_version": "1.0.0",
                    "scenario_id": "demo_scn",
                    "steps": [
                        {"motion_id": "wave_v1", "transition": {"type": "on_complete"}}
                    ],
                },
            )
            _write_json(
                root / "reference_trajectory.json",
                {
                    "schema_version": "1.0.0",
                    "units": {"angle": "radians", "time": "seconds"},
                    "robot_model": "g1_29dof",
                    "frequency_hz": 50,
                    "root_model": "root_not_in_reference",
                    "joint_order": ["0", "1"],
                    "joint_positions": [[0.0, 0.1], [0.2, 0.3]],
                },
            )
            _write_json(
                root / "demonstration_dataset.json",
                {
                    "schema_version": "1.0.0",
                    "robot_model": "g1_29dof",
                    "sampling_hz": 200,
                    "obs_schema_ref": "manifest_obs_v1",
                    "episodes": [
                        {
                            "episode_id": "ep1",
                            "steps": [
                                {"obs": [0.0, 0.1], "act": [0.1, 0.2], "done": False},
                                {"obs": [0.2, 0.3], "act": [0.1, 0.2], "done": True},
                            ],
                        }
                    ],
                },
            )

            report = validate_phase0_directory(root)
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["errors"], [])

    def test_invalid_reference_shape_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_json(
                root / "reference_trajectory.json",
                {
                    "schema_version": "1.0.0",
                    "units": {"angle": "radians", "time": "seconds"},
                    "robot_model": "g1_29dof",
                    "frequency_hz": 50,
                    "root_model": "root_not_in_reference",
                    "joint_order": ["0", "1"],
                    "joint_positions": [[0.0], [0.2, 0.3]],
                },
            )

            report = validate_phase0_directory(root)
            self.assertEqual(report["status"], "error")
            self.assertTrue(any("joint_positions" in err for err in report["errors"]))


if __name__ == "__main__":
    unittest.main()
