"""CLI for NMR (Neural Motion Retargeting) trajectory correction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skill-foundry-nmr",
        description="Correct user-generated trajectories for G1 robot",
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    fix_parser = subparsers.add_parser(
        "fix-collisions",
        help="Fix self-collisions in trajectory",
    )
    fix_parser.add_argument(
        "reference",
        type=Path,
        help="Path to reference trajectory JSON",
    )
    fix_parser.add_argument(
        "--mjcf",
        type=Path,
        required=True,
        help="Path to G1 MJCF scene",
    )
    fix_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path (default: <input>_fixed.json)",
    )
    fix_parser.add_argument(
        "--max-iterations",
        type=int,
        default=50,
        help="Max correction iterations per frame",
    )
    fix_parser.add_argument(
        "--step-size",
        type=float,
        default=0.02,
        help="Correction step size (radians)",
    )
    
    ik_parser = subparsers.add_parser(
        "fix-limits",
        help="Correct joint limit violations using IK",
    )
    ik_parser.add_argument(
        "reference",
        type=Path,
        help="Path to reference trajectory JSON",
    )
    ik_parser.add_argument(
        "--urdf",
        type=Path,
        default=None,
        help="Path to G1 URDF (uses default if not specified)",
    )
    ik_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path (default: <input>_ik.json)",
    )
    
    full_parser = subparsers.add_parser(
        "correct",
        help="Full correction pipeline (IK + collision fix)",
    )
    full_parser.add_argument(
        "reference",
        type=Path,
        help="Path to reference trajectory JSON",
    )
    full_parser.add_argument(
        "--mjcf",
        type=Path,
        required=True,
        help="Path to G1 MJCF scene",
    )
    full_parser.add_argument(
        "--urdf",
        type=Path,
        default=None,
        help="Path to G1 URDF",
    )
    full_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path (default: <input>_corrected.json)",
    )
    
    args = parser.parse_args()
    
    if not args.reference.exists():
        print(f"Error: File not found: {args.reference}", file=sys.stderr)
        return 1
    
    with args.reference.open() as f:
        reference = json.load(f)
    
    if args.command == "fix-collisions":
        from skill_foundry_nmr.collision_fixer import fix_reference_trajectory
        
        if not args.mjcf.exists():
            print(f"Error: MJCF not found: {args.mjcf}", file=sys.stderr)
            return 1
        
        print(f"Fixing collisions in: {args.reference}")
        result = fix_reference_trajectory(
            reference,
            str(args.mjcf),
            max_iterations_per_frame=args.max_iterations,
            step_size=args.step_size,
        )
        
        meta = result.get("_nmr_metadata", {})
        print(f"  Frames fixed: {meta.get('frames_fixed', 0)}")
        print(f"  Total corrections: {meta.get('total_corrections', 0)}")
        
        output = args.output or args.reference.with_stem(args.reference.stem + "_fixed")
        
    elif args.command == "fix-limits":
        from skill_foundry_nmr.ik_corrector import correct_reference_trajectory
        
        print(f"Correcting joint limits in: {args.reference}")
        result = correct_reference_trajectory(
            reference,
            urdf_path=str(args.urdf) if args.urdf else None,
        )
        
        meta = result.get("_ik_metadata", {})
        print(f"  Frames corrected: {meta.get('frames_corrected', 0)}")
        print(f"  Joint limit violations: {meta.get('joint_limit_violations', 0)}")
        
        output = args.output or args.reference.with_stem(args.reference.stem + "_ik")
        
    elif args.command == "correct":
        from skill_foundry_nmr.collision_fixer import fix_reference_trajectory
        from skill_foundry_nmr.ik_corrector import correct_reference_trajectory
        
        if not args.mjcf.exists():
            print(f"Error: MJCF not found: {args.mjcf}", file=sys.stderr)
            return 1
        
        print(f"Full correction pipeline for: {args.reference}")
        
        print("  Step 1: Correcting joint limits...")
        result = correct_reference_trajectory(
            reference,
            urdf_path=str(args.urdf) if args.urdf else None,
        )
        ik_meta = result.get("_ik_metadata", {})
        print(f"    Joint limit violations fixed: {ik_meta.get('joint_limit_violations', 0)}")
        
        print("  Step 2: Fixing self-collisions...")
        result = fix_reference_trajectory(result, str(args.mjcf))
        nmr_meta = result.get("_nmr_metadata", {})
        print(f"    Collision frames fixed: {nmr_meta.get('frames_fixed', 0)}")
        
        result["_correction_pipeline"] = {
            "ik_corrections": ik_meta,
            "collision_fixes": nmr_meta,
        }
        
        output = args.output or args.reference.with_stem(args.reference.stem + "_corrected")
    
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved to: {output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
