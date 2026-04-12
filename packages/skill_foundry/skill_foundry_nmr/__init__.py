"""NMR (Neural Motion Retargeting) — trajectory correction for G1 robot.

Provides IK-based correction and self-collision fixing for user-generated animations.
"""

from skill_foundry_nmr.collision_fixer import (
    CollisionFixResult,
    fix_reference_trajectory,
    fix_self_collisions,
)
from skill_foundry_nmr.ik_corrector import (
    IKCorrectionResult,
    correct_joint_limits,
    correct_reference_trajectory,
    correct_trajectory_ik,
)

__all__ = [
    "CollisionFixResult",
    "IKCorrectionResult",
    "correct_joint_limits",
    "correct_reference_trajectory",
    "correct_trajectory_ik",
    "fix_reference_trajectory",
    "fix_self_collisions",
]
