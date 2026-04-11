"""
CLI: keyframes.json → ReferenceTrajectory v1 JSON + preprocess run log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from skill_foundry_preprocessing.interpolation import keyframes_to_reference_trajectory


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _try_git_commit(repo_root: Path | None) -> str | None:
    env = os.environ.get("GIT_COMMIT") or os.environ.get("SOURCE_GIT_COMMIT")
    if env:
        return env.strip() or None
    cwd = repo_root if repo_root is not None and repo_root.is_dir() else None
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _package_version() -> str:
    try:
        return metadata.version("unitree_sdk2py")
    except metadata.PackageNotFoundError:
        return "unknown"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convert keyframes.json to dense reference_trajectory.json (ReferenceTrajectory v1).",
    )
    p.add_argument(
        "input",
        type=Path,
        help="Path to keyframes.json (schema 1.0.0)",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output ReferenceTrajectory JSON (default: <input_dir>/reference_trajectory.json)",
    )
    p.add_argument(
        "--frequency-hz",
        type=float,
        default=50.0,
        help="Resampling frequency in Hz (default: 50)",
    )
    p.add_argument(
        "--no-joint-velocities",
        action="store_true",
        help="Omit joint_velocities in output",
    )
    p.add_argument(
        "--run-log",
        type=Path,
        default=None,
        help="Path for preprocess run JSON log (default: <output_dir>/preprocess_run.json)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    input_path = args.input.resolve()
    if not input_path.is_file():
        print(f"error: input is not a file: {input_path}", file=sys.stderr)
        return 2

    out_path = (
        args.output.resolve()
        if args.output is not None
        else input_path.parent / "reference_trajectory.json"
    )
    run_log_path = (
        args.run_log.resolve()
        if args.run_log is not None
        else out_path.parent / "preprocess_run.json"
    )

    with input_path.open("r", encoding="utf-8") as f:
        keyframes_data = json.load(f)

    include_vel = not args.no_joint_velocities
    ref = keyframes_to_reference_trajectory(
        keyframes_data,
        frequency_hz=float(args.frequency_hz),
        include_joint_velocities=include_vel,
    )
    _write_json(out_path, ref)

    input_sha = _sha256_file(input_path)
    repo_guess = input_path.parent
    for _ in range(8):
        if (repo_guess / ".git").exists():
            break
        if repo_guess.parent == repo_guess:
            repo_guess = input_path.parent
            break
        repo_guess = repo_guess.parent

    run_log: dict[str, Any] = {
        "frequency_hz": float(args.frequency_hz),
        "include_joint_velocities": include_vel,
        "input_path": str(input_path),
        "input_sha256": input_sha,
        "output_path": str(out_path),
        "package_name": "unitree_sdk2py",
        "package_version": _package_version(),
        "python_version": sys.version.split()[0],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    gc = _try_git_commit(repo_guess)
    if gc:
        run_log["git_commit"] = gc

    _write_json(run_log_path, run_log)
    print(f"Wrote {out_path}", file=sys.stderr)
    print(f"Wrote {run_log_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
