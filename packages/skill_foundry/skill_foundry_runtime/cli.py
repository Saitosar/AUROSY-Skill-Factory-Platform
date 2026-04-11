"""CLI: ``skill-foundry-runtime run`` — MuJoCo or G1 DDS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skill_foundry_export.manifest import DEFAULT_ROBOT_PROFILE
from skill_foundry_sim.reference_loader import load_reference_trajectory_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill-foundry-runtime",
        description="Skill Foundry Phase 4.2: run exported policy + PD from a skill package.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run closed-loop skill")
    run_p.add_argument(
        "--package",
        type=Path,
        required=True,
        help="Skill package directory or .tar.gz",
    )
    run_p.add_argument(
        "--mjcf",
        type=Path,
        required=True,
        help="Local path to the same MJCF used in training (SHA checked vs manifest).",
    )
    run_p.add_argument(
        "--reference",
        type=Path,
        default=None,
        help="Override ReferenceTrajectory v1 JSON (must match provenance.reference_sha256).",
    )
    run_p.add_argument(
        "--mode",
        choices=("mujoco", "dds"),
        default="mujoco",
        help="mujoco: simulation; dds: Unitree G1 low-level (hardware).",
    )
    run_p.add_argument(
        "--network",
        type=str,
        default=None,
        help="DDS network interface (e.g. eth0); passed to ChannelFactoryInitialize.",
    )
    run_p.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Stop after N steps (default: until reference ends).",
    )
    run_p.add_argument(
        "--deterministic",
        action="store_true",
        default=True,
        help="Deterministic policy.predict (default: true).",
    )
    run_p.add_argument(
        "--stochastic",
        action="store_true",
        help="Use stochastic policy.predict (overrides --deterministic).",
    )
    run_p.add_argument(
        "--min-base-height",
        type=float,
        default=0.35,
        help="MuJoCo only: terminate if pelvis z falls below (meters).",
    )
    run_p.add_argument(
        "--max-abs-tau",
        type=float,
        default=120.0,
        help="Per-motor torque clip magnitude (Nm), MuJoCo ctrl.",
    )
    run_p.add_argument(
        "--robot-profile",
        type=str,
        default=None,
        help=f"Require manifest robot.profile (default: {DEFAULT_ROBOT_PROFILE}).",
    )
    run_p.add_argument(
        "--allow-missing-weights-sha256",
        action="store_true",
        help="Allow manifests without weights.sha256 (legacy bundles; not for production).",
    )
    run_p.add_argument(
        "--max-abs-dq",
        type=float,
        default=None,
        help="If set, stop after repeated violations of |motor_dq| or |dq_des| (rad/s). "
        "DDS default 30 if omitted; MuJoCo leaves checks off unless set.",
    )

    args = parser.parse_args(argv)

    if args.cmd != "run":
        return 1

    from skill_foundry_runtime.compatibility import check_compatibility, resolve_reference_path
    from skill_foundry_runtime.package_loader import open_skill_package
    from skill_foundry_runtime.policy_sb3 import load_ppo_policy

    profile = args.robot_profile or DEFAULT_ROBOT_PROFILE

    with open_skill_package(args.package) as pkg:
        errs = check_compatibility(
            pkg.manifest,
            package_root=pkg.root,
            mjcf_path=args.mjcf,
            reference_path=resolve_reference_path(pkg.root, pkg.manifest, args.reference),
            expected_profile=profile,
            allow_missing_weights_sha256=bool(args.allow_missing_weights_sha256),
        )
        if errs:
            for e in errs:
                print(f"compatibility error: {e}", file=sys.stderr)
            return 2

        ref_path = resolve_reference_path(pkg.root, pkg.manifest, args.reference)
        reference = load_reference_trajectory_json(ref_path)
        ckpt = pkg.weights_path()
        policy = load_ppo_policy(ckpt)

        det = not args.stochastic

        if args.mode == "mujoco":
            from skill_foundry_runtime.loop_mujoco import run_mujoco_skill_loop
            from skill_foundry_runtime.safety import SafetyConfig

            max_dq = args.max_abs_dq
            s_cfg = SafetyConfig(max_abs_tau=float(args.max_abs_tau), max_abs_dq=max_dq)
            res = run_mujoco_skill_loop(
                mjcf_path=str(args.mjcf.resolve()),
                reference=reference,
                manifest=pkg.manifest,
                policy=policy,
                max_steps=args.max_steps,
                deterministic_policy=det,
                min_base_height=float(args.min_base_height),
                safety_cfg=s_cfg,
            )
            print(
                json.dumps(
                    {
                        "mode": "mujoco",
                        "steps": res.steps,
                        "stopped": res.stopped,
                        "stop_reason": res.stop_reason,
                        "final_episode_time_s": res.final_episode_time_s,
                    },
                    indent=2,
                )
            )
            return 0

        print(
            "WARNING: DDS mode moves a real robot. Clear the area and keep e-stop ready.",
            file=sys.stderr,
        )
        from skill_foundry_runtime.dds_g1 import DDSRunConfig, run_dds_g1_skill_loop

        dds_cfg = DDSRunConfig(
            network_interface=args.network,
            max_steps=args.max_steps,
            deterministic_policy=det,
        )
        max_dq = float(args.max_abs_dq) if args.max_abs_dq is not None else 30.0
        s_cfg = SafetyConfig(max_abs_tau=float(args.max_abs_tau), max_abs_dq=max_dq)
        n = run_dds_g1_skill_loop(
            reference=reference,
            manifest=pkg.manifest,
            policy=policy,
            cfg=dds_cfg,
            safety_cfg=s_cfg,
        )
        print(json.dumps({"mode": "dds", "steps": n}, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
