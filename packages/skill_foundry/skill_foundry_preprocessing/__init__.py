"""Skill Foundry: keyframes → dense ReferenceTrajectory (phase 1.1)."""

from skill_foundry_preprocessing.interpolation import (
    CANONICAL_JOINT_ORDER,
    keyframes_to_reference_trajectory,
)

__all__ = [
    "CANONICAL_JOINT_ORDER",
    "keyframes_to_reference_trajectory",
]
