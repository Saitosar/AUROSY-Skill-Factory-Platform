"""CLI: ``skill-foundry-package`` — pack manifest + checkpoint (+ optional ONNX / policy .pt)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected JSON object in {path}")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill-foundry-package",
        description="Skill Foundry Phase 4.1: build manifest and skill package archive.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    pack_p = sub.add_parser("pack", help="Create manifest.json + tar.gz with weights")
    pack_p.add_argument(
        "--train-config",
        type=Path,
        required=True,
        help="Training config JSON (same as skill-foundry-train).",
    )
    pack_p.add_argument(
        "--reference-trajectory",
        type=Path,
        required=True,
        help="ReferenceTrajectory v1 JSON used for training.",
    )
    pack_p.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Directory containing train_run.json and ppo_G1TrackingEnv.zip.",
    )
    pack_p.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output archive path (.tar.gz).",
    )
    pack_p.add_argument(
        "--package-version",
        type=str,
        default=None,
        help="Semver for export format (default: 1.0.0).",
    )
    pack_p.add_argument(
        "--robot-profile",
        type=str,
        default=None,
        help="Robot profile id (default: unitree_g1_29dof).",
    )
    pack_p.add_argument(
        "--policy-pt",
        action="store_true",
        help="Also write policy_weights.pt (policy state_dict).",
    )
    pack_p.add_argument(
        "--onnx",
        action="store_true",
        help="Also export policy.onnx (requires onnx).",
    )
    pack_p.add_argument(
        "--onnx-opset",
        type=int,
        default=17,
        help="ONNX opset version (default: 17).",
    )
    pack_p.add_argument(
        "--include-amp-discriminator",
        action="store_true",
        help="Copy amp_discriminator.pt into the archive when present (Phase 5).",
    )
    pack_p.add_argument(
        "--joint-map-version",
        type=str,
        default="1.0",
        help="Retarget joint_map version recorded in manifest.motion (default: 1.0).",
    )
    pack_p.add_argument(
        "--motion-source-skeleton",
        type=str,
        default="mediapipe_pose_33",
        help="Source skeleton id for manifest.motion.retarget_profile.",
    )
    pack_p.add_argument(
        "--record-motion-metadata",
        action="store_true",
        help=(
            "Include manifest.motion retarget defaults even when no eval_motion.json / AMP run "
            "(optional branding)."
        ),
    )

    args = parser.parse_args(argv)

    if args.cmd == "pack":
        from skill_foundry_export.packaging import package_skill

        cfg = _load_json(args.train_config)
        motion_export = None
        if args.record_motion_metadata:
            motion_export = {
                "joint_map_version": args.joint_map_version,
                "source_skeleton": args.motion_source_skeleton,
            }
        summary = package_skill(
            train_config=cfg,
            reference_path=args.reference_trajectory,
            run_dir=args.run_dir,
            output_archive=args.output,
            train_config_path=args.train_config.resolve(),
            package_version=args.package_version,
            robot_profile=args.robot_profile,
            include_policy_pt=args.policy_pt,
            include_onnx=args.onnx,
            onnx_opset=args.onnx_opset,
            motion_export=motion_export,
            include_amp_discriminator=args.include_amp_discriminator,
        )
        print(json.dumps(summary, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
