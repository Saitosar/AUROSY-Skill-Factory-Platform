"""Reference motion helpers for AMP-style expert transition sampling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from skill_foundry_sim.trajectory_sampler import sample_trajectory_at_times

NU = 29


@dataclass(frozen=True)
class ReferenceMotion:
    """Time-indexed reference trajectory representation."""

    frequency_hz: float
    joint_order: list[str]
    joint_positions: list[list[float]]
    joint_velocities: list[list[float]] | None = None

    @property
    def dt(self) -> float:
        return 1.0 / self.frequency_hz

    @property
    def num_samples(self) -> int:
        return len(self.joint_positions)

    @property
    def duration_sec(self) -> float:
        if self.num_samples < 2:
            return 0.0
        return float(self.num_samples - 1) / float(self.frequency_hz)

    def sample_joint_rows(self, times_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Interpolate q/dq for requested times (shape: [N, D])."""
        return sample_trajectory_at_times(
            self.joint_positions,
            self.frequency_hz,
            np.asarray(times_s, dtype=np.float64),
            joint_velocities=self.joint_velocities,
        )

    def to_motor_rows(self, q_cols: np.ndarray, dq_cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Project trajectory columns to 29 motor-order rows."""
        n = q_cols.shape[0]
        q = np.zeros((n, NU), dtype=np.float64)
        dq = np.zeros((n, NU), dtype=np.float64)
        for col, jid_str in enumerate(self.joint_order):
            mi = int(str(jid_str))
            if 0 <= mi < NU:
                q[:, mi] = q_cols[:, col]
                dq[:, mi] = dq_cols[:, col]
        return q, dq

    def sample_expert_states(self, rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray]:
        """Sample expert transitions in RL obs layout: [q, dq, q_err]."""
        if n < 1:
            raise ValueError("n must be >= 1")
        if self.duration_sec <= 0.0:
            t0 = np.zeros((n,), dtype=np.float64)
        else:
            t0 = rng.uniform(0.0, self.duration_sec, size=n).astype(np.float64)
        t1 = np.clip(t0 + self.dt, 0.0, self.duration_sec).astype(np.float64)
        q0_cols, dq0_cols = self.sample_joint_rows(t0)
        q1_cols, dq1_cols = self.sample_joint_rows(t1)
        q0, dq0 = self.to_motor_rows(q0_cols, dq0_cols)
        q1, dq1 = self.to_motor_rows(q1_cols, dq1_cols)

        z = np.zeros_like(q0)
        s0 = np.concatenate([q0, dq0, z], axis=1)
        s1 = np.concatenate([q1, dq1, z], axis=1)
        return s0, s1


def reference_motion_from_dict(reference: dict[str, Any]) -> ReferenceMotion:
    """Build ReferenceMotion from validated ReferenceTrajectory v1 payload."""
    return ReferenceMotion(
        frequency_hz=float(reference["frequency_hz"]),
        joint_order=[str(v) for v in reference["joint_order"]],
        joint_positions=reference["joint_positions"],
        joint_velocities=reference.get("joint_velocities"),
    )
