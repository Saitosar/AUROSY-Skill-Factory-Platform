"""
Convert 12-DOF rollout from Unitree policy to ReferenceTrajectory v1 (29 DOF).

Mapping strategy:
- Indices 0-11 (legs): from rollout
- Indices 12-14 (waist): hold at 0
- Indices 15-28 (arms): hold at neutral arm pose
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


CANONICAL_JOINT_ORDER_29 = [
    "0",  # left_hip_pitch
    "1",  # left_hip_roll
    "2",  # left_hip_yaw
    "3",  # left_knee
    "4",  # left_ankle_pitch
    "5",  # left_ankle_roll
    "6",  # right_hip_pitch
    "7",  # right_hip_roll
    "8",  # right_hip_yaw
    "9",  # right_knee
    "10",  # right_ankle_pitch
    "11",  # right_ankle_roll
    "12",  # waist_yaw
    "13",  # waist_roll
    "14",  # waist_pitch
    "15",  # left_shoulder_pitch
    "16",  # left_shoulder_roll
    "17",  # left_shoulder_yaw
    "18",  # left_elbow
    "19",  # left_wrist_roll
    "20",  # left_wrist_pitch
    "21",  # left_wrist_yaw
    "22",  # right_shoulder_pitch
    "23",  # right_shoulder_roll
    "24",  # right_shoulder_yaw
    "25",  # right_elbow
    "26",  # right_wrist_roll
    "27",  # right_wrist_pitch
    "28",  # right_wrist_yaw
]

NEUTRAL_ARM_ANGLES_RAD = {
    15: 0.0,   # left_shoulder_pitch
    16: 0.2,   # left_shoulder_roll (slightly out)
    17: 0.0,   # left_shoulder_yaw
    18: 0.3,   # left_elbow (slightly bent)
    19: 0.0,   # left_wrist_roll
    20: 0.0,   # left_wrist_pitch
    21: 0.0,   # left_wrist_yaw
    22: 0.0,   # right_shoulder_pitch
    23: -0.2,  # right_shoulder_roll (slightly out, mirrored)
    24: 0.0,   # right_shoulder_yaw
    25: 0.3,   # right_elbow (slightly bent)
    26: 0.0,   # right_wrist_roll
    27: 0.0,   # right_wrist_pitch
    28: 0.0,   # right_wrist_yaw
}


def expand_12dof_to_29dof(positions_12: np.ndarray) -> np.ndarray:
    """
    Expand [T, 12] leg-only positions to [T, 29] full body.

    Args:
        positions_12: Joint positions from Unitree 12-DOF policy (legs only)

    Returns:
        positions_29: Full 29-DOF positions with neutral arms and waist
    """
    T = positions_12.shape[0]
    positions_29 = np.zeros((T, 29), dtype=np.float64)

    positions_29[:, 0:12] = positions_12

    for idx, angle in NEUTRAL_ARM_ANGLES_RAD.items():
        positions_29[:, idx] = angle

    return positions_29


def build_reference_trajectory(
    positions_29: np.ndarray,
    timestamps_s: np.ndarray,
    source_metadata: dict,
) -> dict:
    """
    Build ReferenceTrajectory v1 dict.

    Args:
        positions_29: [T, 29] joint positions in radians
        timestamps_s: [T] timestamps
        source_metadata: Provenance info from rollout

    Returns:
        ReferenceTrajectory v1 dict ready for JSON serialization
    """
    if len(timestamps_s) < 2:
        raise ValueError("Need at least 2 frames")

    dt = np.diff(timestamps_s).mean()
    frequency_hz = 1.0 / dt

    return {
        "schema_version": "1.0.0",
        "units": {"angle": "radians", "time": "seconds"},
        "frequency_hz": float(frequency_hz),
        "joint_order": CANONICAL_JOINT_ORDER_29,
        "joint_positions": positions_29.tolist(),
        "root_model": "root_not_in_reference",
        "metadata": {
            "source": "unitree_rl_gym/deploy/pre_train/g1/motion.pt",
            "conversion": "12-DOF legs → 29-DOF (waist=0, arms=neutral)",
            "upstream_commit": source_metadata.get("upstream_commit", "unknown"),
            "converted_at": datetime.now(timezone.utc).isoformat(),
            "original_duration_s": float(timestamps_s[-1]),
            "original_hz": source_metadata.get("output_hz", frequency_hz),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert 12-DOF rollout to ReferenceTrajectory v1")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent / "rollout_12dof.npz",
        help="Input .npz from rollout_recorder.py",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output reference_trajectory.json path",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(f"Input not found: {args.input}")

    data = np.load(args.input)
    positions_12 = data["joint_positions"]
    timestamps_s = data["timestamps_s"]

    meta_path = args.input.with_suffix(".meta.json")
    if meta_path.is_file():
        with meta_path.open() as f:
            source_metadata = json.load(f)
    else:
        source_metadata = {}

    print(f"Input: {args.input}")
    print(f"  Shape: {positions_12.shape}, duration: {timestamps_s[-1]:.2f}s")

    positions_29 = expand_12dof_to_29dof(positions_12)
    ref = build_reference_trajectory(positions_29, timestamps_s, source_metadata)

    out_path = args.output or args.input.parent / "reference_trajectory.json"
    with out_path.open("w") as f:
        json.dump(ref, f, indent=2)

    print(f"Output: {out_path}")
    print(f"  Frames: {len(ref['joint_positions'])}, frequency_hz: {ref['frequency_hz']:.1f}")


if __name__ == "__main__":
    main()
