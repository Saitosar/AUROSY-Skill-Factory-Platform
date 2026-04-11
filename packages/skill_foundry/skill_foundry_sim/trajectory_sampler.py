"""Interpolate joint_positions (and optional joint_velocities) onto arbitrary sample times."""

from __future__ import annotations

import numpy as np


def sample_trajectory_at_times(
    joint_positions: list[list[float]],
    frequency_hz: float,
    sample_times_s: np.ndarray,
    joint_velocities: list[list[float]] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Linear interpolation in time between reference rows.

    Reference sample k is at time k / frequency_hz for k in 0..T-1.

    Parameters
    ----------
    joint_positions
        Shape [T, D] as nested lists.
    frequency_hz
        Sampling rate of the reference (must match contract).
    sample_times_s
        1-D array of times at which to evaluate (seconds).

    Returns
    -------
    q, dq
        Arrays of shape (len(sample_times_s), D). If joint_velocities is absent, dq is zeros.
    """
    jp = np.asarray(joint_positions, dtype=np.float64)
    if jp.ndim != 2:
        raise ValueError("joint_positions must be 2-D after conversion")
    t_samples, _d = jp.shape
    if t_samples == 0:
        raise ValueError("joint_positions must be non-empty")
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")

    t_max = (t_samples - 1) / frequency_hz
    st = np.asarray(sample_times_s, dtype=np.float64)
    st = np.clip(st, 0.0, t_max)
    idx_f = st * frequency_hz
    i0 = np.floor(idx_f).astype(np.int32)
    i1 = np.minimum(i0 + 1, t_samples - 1)
    alpha = idx_f - i0.astype(np.float64)
    q = (1.0 - alpha)[:, np.newaxis] * jp[i0] + alpha[:, np.newaxis] * jp[i1]

    if joint_velocities is not None:
        jv = np.asarray(joint_velocities, dtype=np.float64)
        if jv.shape != jp.shape:
            raise ValueError("joint_velocities must match joint_positions shape")
        dq = (1.0 - alpha)[:, np.newaxis] * jv[i0] + alpha[:, np.newaxis] * jv[i1]
    else:
        dq = np.zeros_like(q)

    return q, dq
