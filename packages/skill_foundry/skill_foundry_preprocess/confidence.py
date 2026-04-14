"""Confidence normalization and missing-value preparation helpers."""

from __future__ import annotations

import numpy as np

LANDMARK_COUNT = 33


def normalize_confidences(confidences: np.ndarray, frame_count: int) -> np.ndarray:
    """Normalize confidence tensors to shape ``[N, 33]``."""
    arr = np.asarray(confidences, dtype=np.float32)
    if arr.ndim == 0:
        return np.full((frame_count, LANDMARK_COUNT), float(arr), dtype=np.float32)
    if arr.ndim == 1:
        if arr.shape[0] != frame_count:
            raise ValueError("confidences with shape [N] must match frame count")
        return np.repeat(arr[:, np.newaxis], LANDMARK_COUNT, axis=1)
    if arr.ndim == 2:
        if arr.shape[0] != frame_count:
            raise ValueError("confidence frame count mismatch")
        if arr.shape[1] == 1:
            return np.repeat(arr, LANDMARK_COUNT, axis=1)
        if arr.shape[1] != LANDMARK_COUNT:
            raise ValueError("confidences with shape [N, M] require M==33")
        return arr
    raise ValueError("confidences must have shape [N], [N,1], or [N,33]")


def apply_confidence_mask(
    landmarks: np.ndarray,
    confidences_2d: np.ndarray,
    *,
    threshold: float,
) -> np.ndarray:
    """Set low-confidence landmark values to ``NaN`` for gap filling."""
    if landmarks.ndim != 3 or landmarks.shape[1:] != (LANDMARK_COUNT, 3):
        raise ValueError("landmarks must have shape [N, 33, 3]")
    if confidences_2d.shape != landmarks.shape[:2]:
        raise ValueError("confidences must have shape [N, 33]")
    out = np.asarray(landmarks, dtype=np.float32).copy()
    if threshold <= 0:
        return out
    low_conf_mask = confidences_2d < float(threshold)
    out[low_conf_mask, :] = np.nan
    return out


def interpolate_nans_1d(series: np.ndarray) -> np.ndarray:
    """Linearly interpolate NaN values in a 1D signal."""
    x = np.asarray(series, dtype=np.float32).copy()
    if x.ndim != 1:
        raise ValueError("series must be 1D")
    n = x.shape[0]
    if n == 0:
        return x
    mask = np.isnan(x)
    if not np.any(mask):
        return x
    valid = ~mask
    if not np.any(valid):
        return np.zeros_like(x)
    idx = np.arange(n, dtype=np.float32)
    x[mask] = np.interp(idx[mask], idx[valid], x[valid]).astype(np.float32)
    return x

