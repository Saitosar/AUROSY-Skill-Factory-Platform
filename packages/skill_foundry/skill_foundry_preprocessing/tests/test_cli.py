import json
import sys
import tempfile
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
SDK_PYTHON_ROOT = TEST_FILE.parents[2]
if str(SDK_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_PYTHON_ROOT))

from skill_foundry_preprocessing.cli import (  # noqa: E402
    _sha256_file,
    build_arg_parser,
    main,
)


_MINIMAL_KEYFRAMES = {
    "schema_version": "1.0.0",
    "units": {"angle": "degrees", "time": "seconds"},
    "keyframes": [
        {"timestamp_s": 0.0, "joints_deg": {"0": 0.0}},
        {"timestamp_s": 1.0, "joints_deg": {"0": 30.0}},
    ],
}


class TestCli(unittest.TestCase):
    def test_main_writes_reference_and_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            inp = td_path / "keyframes.json"
            inp.write_text(json.dumps(_MINIMAL_KEYFRAMES), encoding="utf-8")
            out = td_path / "reference_trajectory.json"
            log = td_path / "preprocess_run.json"

            rc = main(
                [
                    str(inp),
                    "-o",
                    str(out),
                    "--run-log",
                    str(log),
                    "--frequency-hz",
                    "10",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out.is_file())
            self.assertTrue(log.is_file())

            with out.open(encoding="utf-8") as f:
                ref = json.load(f)
            self.assertEqual(ref["schema_version"], "1.0.0")
            self.assertIn("joint_positions", ref)
            self.assertIn("joint_velocities", ref)
            self.assertEqual(ref["frequency_hz"], 10.0)

            with log.open(encoding="utf-8") as f:
                run = json.load(f)
            self.assertEqual(run["frequency_hz"], 10.0)
            self.assertTrue(run["include_joint_velocities"])
            self.assertEqual(run["input_sha256"], _sha256_file(inp))
            self.assertEqual(run["input_path"], str(inp.resolve()))
            self.assertEqual(run["output_path"], str(out.resolve()))
            self.assertIn("timestamp_utc", run)
            self.assertIn("python_version", run)
            self.assertIn("package_version", run)

    def test_main_no_joint_velocities(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            inp = td_path / "keyframes.json"
            inp.write_text(json.dumps(_MINIMAL_KEYFRAMES), encoding="utf-8")
            out = td_path / "ref.json"

            rc = main([str(inp), "-o", str(out), "--no-joint-velocities", "--frequency-hz", "5"])
            self.assertEqual(rc, 0)
            with out.open(encoding="utf-8") as f:
                ref = json.load(f)
            self.assertNotIn("joint_velocities", ref)

            log = td_path / "preprocess_run.json"
            with log.open(encoding="utf-8") as f:
                run = json.load(f)
            self.assertFalse(run["include_joint_velocities"])

    def test_reference_output_deterministic_on_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            inp = td_path / "keyframes.json"
            inp.write_text(json.dumps(_MINIMAL_KEYFRAMES), encoding="utf-8")
            out = td_path / "reference_trajectory.json"

            rc1 = main([str(inp), "-o", str(out), "--frequency-hz", "10"])
            text1 = out.read_text(encoding="utf-8")
            rc2 = main([str(inp), "-o", str(out), "--frequency-hz", "10"])
            text2 = out.read_text(encoding="utf-8")

            self.assertEqual(rc1, 0)
            self.assertEqual(rc2, 0)
            self.assertEqual(text1, text2)

    def test_missing_input_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nope.json"
            rc = main([str(missing)])
            self.assertEqual(rc, 2)

    def test_arg_parser_defaults(self) -> None:
        p = build_arg_parser()
        args = p.parse_args([str(Path("/tmp/k.json"))])
        self.assertEqual(args.frequency_hz, 50.0)
        self.assertFalse(args.no_joint_velocities)
        self.assertIsNone(args.output)
        self.assertIsNone(args.run_log)


if __name__ == "__main__":
    unittest.main()
