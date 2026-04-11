"""CLI: headless ReferenceTrajectory playback and log export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skill_foundry_sim.demonstration_dataset import (
    build_demonstration_dataset,
    find_git_root,
    write_demonstration_dataset_json,
)
from skill_foundry_sim.headless_playback import PlaybackConfig, run_headless_playback
from skill_foundry_sim.log_compare import compare_playback_logs, load_playback_log, save_playback_log
from skill_foundry_sim.reference_loader import load_reference_trajectory_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Play ReferenceTrajectory v1 in MuJoCo G1 (headless) and save a reproducibility log.",
    )
    parser.add_argument(
        "reference",
        type=Path,
        help="Path to reference_trajectory.json",
    )
    parser.add_argument(
        "--mjcf",
        type=Path,
        required=True,
        help="Path to MJCF (e.g. unitree_mujoco/unitree_robots/g1/scene_29dof.xml)",
    )
    parser.add_argument(
        "--mode",
        choices=("dynamic", "kinematic"),
        default="dynamic",
        help="dynamic: PD tracking like unitree_mujoco bridge; kinematic: qpos + mj_forward only",
    )
    parser.add_argument("--dt", type=float, default=0.005, help="Simulation timestep (seconds)")
    parser.add_argument("--kp", type=float, default=150.0)
    parser.add_argument("--kd", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output log path (.npz)",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        help="Optional second .npz to compare after run (exit 1 if mismatch)",
    )
    parser.add_argument(
        "--demonstration-json",
        type=Path,
        default=None,
        help="Optional path to write demonstration_dataset.json (DemonstrationDataset v1)",
    )
    parser.add_argument(
        "--no-ref",
        action="store_true",
        help="With --demonstration-json: omit per-step ref targets",
    )
    parser.add_argument(
        "--episode-id",
        type=str,
        default="ep_0001",
        help="Episode id in demonstration_dataset.json (default: ep_0001)",
    )
    args = parser.parse_args(argv)

    ref = load_reference_trajectory_json(args.reference)
    cfg = PlaybackConfig(
        mjcf_path=str(args.mjcf.resolve()),
        sim_dt=args.dt,
        mode=args.mode,
        kp=args.kp,
        kd=args.kd,
        seed=args.seed,
        max_steps=args.max_steps,
    )
    log = run_headless_playback(ref, cfg)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_playback_log(args.output, log)

    meta_out = {**log.meta, "output_log": str(args.output.resolve())}
    if args.demonstration_json is not None:
        git_root = find_git_root(args.mjcf) or find_git_root(args.reference)
        demo = build_demonstration_dataset(
            log,
            robot_model=str(ref.get("robot_model", "g1_29dof")),
            sim_dt=args.dt,
            seed=args.seed,
            repo_root_for_git=git_root,
            episode_id=args.episode_id,
            include_ref=not args.no_ref,
        )
        write_demonstration_dataset_json(args.demonstration_json, demo)
        meta_out["demonstration_dataset"] = str(args.demonstration_json.resolve())
        meta_out["obs_schema_ref"] = demo["obs_schema_ref"]
    print(json.dumps(meta_out, indent=2))

    if args.compare is not None:
        other = load_playback_log(args.compare)
        cur = {
            "time_s": log.time_s,
            "motor_q": log.motor_q,
            "motor_dq": log.motor_dq,
            "ctrl": log.ctrl,
        }
        ok, msgs = compare_playback_logs(cur, other)
        if not ok:
            for m in msgs:
                print(m, file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
