"""Signal smoothing utilities for retargeted joint trajectories."""

from __future__ import annotations

import numpy as np


def ema_smooth(sequence: np.ndarray, alpha: float = 0.6) -> np.ndarray:
    if sequence.ndim != 2:
        raise ValueError("expected [N, D] sequence")
    if sequence.shape[0] == 0:
        raise ValueError("sequence must contain at least one frame")
    if not (0.0 < alpha <= 1.0):
        raise ValueError("alpha must be in (0, 1]")
    out = np.empty_like(sequence, dtype=np.float32)
    out[0] = sequence[0]
    for i in range(1, sequence.shape[0]):
        out[i] = (alpha * sequence[i]) + ((1.0 - alpha) * out[i - 1])
    return out
