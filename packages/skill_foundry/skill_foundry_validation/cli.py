"""CLI: ``skill-foundry-validate-motion`` — validate a ReferenceTrajectory JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skill_foundry_validation.motion_validator import MotionValidatorConfig, validate_reference_motion_from_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate ReferenceTrajectory v1 (kinematics, RNEA, MuJoCo collision)")
    p.add_argument("reference_json", type=Path, help="Path to reference_trajectory.json")
    p.add_argument("--mjcf", type=Path, default=None, help="MJCF path for self-collision (e.g. scene_29dof.xml)")
    p.add_argument("--urdf", type=Path, default=None, help="Override URDF for Pinocchio RNEA")
    p.add_argument("--no-collision", action="store_true", help="Skip MuJoCo collision")
    p.add_argument("--no-torque", action="store_true", help="Skip Pinocchio RNEA torque")
    p.add_argument("--no-kinematics", action="store_true", help="Skip joint limit / accel checks")
    p.add_argument("--collision-stride", type=int, default=1, help="Sample every N frames for collision")
    p.add_argument("--torque-stride", type=int, default=5, help="Sample every N frames for RNEA")
    p.add_argument("-o", "--output", type=Path, default=None, help="Write validation_report.json")
    args = p.parse_args(argv)

    cfg = MotionValidatorConfig(
        check_kinematics=not args.no_kinematics,
        check_collision=not args.no_collision,
        check_torque_rnea=not args.no_torque,
        collision_frame_stride=max(1, args.collision_stride),
        torque_frame_stride=max(1, args.torque_stride),
        mjcf_path=str(args.mjcf) if args.mjcf else None,
        urdf_path=str(args.urdf) if args.urdf else None,
    )

    report = validate_reference_motion_from_path(args.reference_json, config=cfg)
    text = json.dumps(report.to_dict(), indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
