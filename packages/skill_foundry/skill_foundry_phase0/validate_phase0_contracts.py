#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from skill_foundry_phase0.contract_validator import validate_phase0_directory


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Skill Foundry Phase 0 contract bundle.")
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=Path("docs/skill_foundry/golden/v1"),
        help="Directory containing keyframes.json, motion.json, scenario.json, reference_trajectory.json, demonstration_dataset.json",
    )
    args = parser.parse_args()

    report = validate_phase0_directory(args.bundle_dir)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

