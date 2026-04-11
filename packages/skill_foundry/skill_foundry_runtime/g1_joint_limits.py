"""G1 29-DoF joint position limits in **motor / actuator order** from ``g1_29dof.xml``.

Matches MuJoCo ``<actuator>`` motor list (same order as training / ReferenceTrajectory columns).
"""

from __future__ import annotations

import numpy as np

# From unitree_mujoco/unitree_robots/g1/g1_29dof.xml — joint ``range`` per motor row.
G1_29DOF_Q_LOW = np.array(
    [
        -2.5307,
        -0.5236,
        -2.7576,
        -0.087267,
        -0.87267,
        -0.2618,
        -2.5307,
        -2.9671,
        -2.7576,
        -0.087267,
        -0.87267,
        -0.2618,
        -2.618,
        -0.52,
        -0.52,
        -3.0892,
        -1.5882,
        -2.618,
        -1.0472,
        -1.97222,
        -1.61443,
        -1.61443,
        -3.0892,
        -2.2515,
        -2.618,
        -1.0472,
        -1.97222,
        -1.61443,
        -1.61443,
    ],
    dtype=np.float64,
)

G1_29DOF_Q_HIGH = np.array(
    [
        2.8798,
        2.9671,
        2.7576,
        2.8798,
        0.5236,
        0.2618,
        2.8798,
        0.5236,
        2.7576,
        2.8798,
        0.5236,
        0.2618,
        2.618,
        0.52,
        0.52,
        2.6704,
        2.2515,
        2.618,
        2.0944,
        1.97222,
        1.61443,
        1.61443,
        2.6704,
        1.5882,
        2.618,
        2.0944,
        1.97222,
        1.61443,
        1.61443,
    ],
    dtype=np.float64,
)


def g1_29dof_motor_q_limits() -> tuple[np.ndarray, np.ndarray]:
    """Return ``(q_low, q_high)`` shape (29,) for DDS / hardware safety (radians)."""
    return G1_29DOF_Q_LOW.copy(), G1_29DOF_Q_HIGH.copy()
