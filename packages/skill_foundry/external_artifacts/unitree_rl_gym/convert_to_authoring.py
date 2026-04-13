"""
Convert ReferenceTrajectory v1 to authoring format (keyframes.json + motion.json).

Downsamples dense trajectory to sparse keyframes suitable for UI editing.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def downsample_to_keyframes(
    positions: np.ndarray,
    timestamps_s: np.ndarray,
    target_keyframes: int = 10,
) -> tuple[list[dict], list[float]]:
    """
    Downsample dense trajectory to sparse keyframes.

    Args:
        positions: [T, D] joint positions in radians
        timestamps_s: [T] timestamps
        target_keyframes: Approximate number of keyframes to extract

    Returns:
        (keyframes_list, timestamps_list) where keyframes have joints_deg
    """
    T = len(positions)
    if T <= target_keyframes:
        indices = list(range(T))
    else:
        step = (T - 1) / (target_keyframes - 1)
        indices = [round(i * step) for i in range(target_keyframes)]
        indices[-1] = T - 1

    keyframes = []
    kf_timestamps = []

    for idx in indices:
        joints_deg = {}
        for j, angle_rad in enumerate(positions[idx]):
            joints_deg[str(j)] = round(math.degrees(angle_rad), 2)

        keyframes.append({
            "timestamp_s": round(float(timestamps_s[idx]), 3),
            "joints_deg": joints_deg,
        })
        kf_timestamps.append(round(float(timestamps_s[idx]), 3))

    return keyframes, kf_timestamps


def build_keyframes_json(keyframes: list[dict], robot_model: str = "g1_29dof") -> dict:
    """Build keyframes.json payload."""
    return {
        "schema_version": "1.0.0",
        "robot_model": robot_model,
        "units": {"angle": "degrees", "time": "seconds"},
        "keyframes": keyframes,
    }


def build_motion_json(
    motion_id: str,
    keyframes_id: str,
    timestamps: list[float],
    metadata: dict | None = None,
) -> dict:
    """Build motion.json payload."""
    return {
        "schema_version": "1.0.0",
        "motion_id": motion_id,
        "source_keyframes_id": keyframes_id,
        "keyframe_timestamps_s": timestamps,
        "metadata": metadata or {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert reference_trajectory.json to authoring format")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent / "reference_trajectory.json",
        help="Input reference_trajectory.json",
    )
    parser.add_argument(
        "--keyframes",
        type=int,
        default=10,
        help="Target number of keyframes",
    )
    parser.add_argument(
        "--motion-id",
        type=str,
        default="unitree_walking_v1",
        help="Motion ID for motion.json",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=None,
        help="Output directory for keyframes.json and motion.json",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(f"Input not found: {args.input}")

    with args.input.open() as f:
        ref = json.load(f)

    positions = np.array(ref["joint_positions"])
    frequency_hz = ref["frequency_hz"]
    T = len(positions)
    timestamps_s = np.arange(T) / frequency_hz

    print(f"Input: {args.input}")
    print(f"  Frames: {T}, frequency_hz: {frequency_hz}")

    keyframes, kf_timestamps = downsample_to_keyframes(
        positions, timestamps_s, target_keyframes=args.keyframes
    )

    keyframes_id = f"{args.motion_id}_keyframes"
    kf_json = build_keyframes_json(keyframes)
    motion_json = build_motion_json(
        motion_id=args.motion_id,
        keyframes_id=keyframes_id,
        timestamps=kf_timestamps,
        metadata={
            "source": "unitree_rl_gym/deploy/pre_train/g1/motion.pt",
            "conversion": "12-DOF policy rollout → 29-DOF reference → sparse keyframes",
            "converted_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    out_dir = args.output_dir or args.input.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    kf_path = out_dir / "keyframes.json"
    motion_path = out_dir / "motion.json"

    with kf_path.open("w") as f:
        json.dump(kf_json, f, indent=2)
    with motion_path.open("w") as f:
        json.dump(motion_json, f, indent=2)

    print(f"Output:")
    print(f"  {kf_path} ({len(keyframes)} keyframes)")
    print(f"  {motion_path}")


if __name__ == "__main__":
    main()
