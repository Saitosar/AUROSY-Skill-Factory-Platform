"""Time-series filters for landmark preprocessing."""

from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter

from .confidence import (
    LANDMARK_COUNT,
    apply_confidence_mask,
    interpolate_nans_1d,
    normalize_confidences,
)


def _normalize_landmarks(landmarks: np.ndarray) -> np.ndarray:
    arr = np.asarray(landmarks, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[1:] != (LANDMARK_COUNT, 3):
        raise ValueError("landmarks must have shape [N, 33, 3]")
    if arr.shape[0] < 1:
        raise ValueError("landmarks must contain at least one frame")
    return arr


def _normalize_window(n_frames: int, window_length: int, polyorder: int) -> tuple[int, int]:
    if n_frames < 3:
        return 1, 0
    wl = max(3, int(window_length))
    if wl % 2 == 0:
        wl += 1
    if wl > n_frames:
        wl = n_frames if n_frames % 2 == 1 else n_frames - 1
    po = max(0, int(polyorder))
    if wl <= 1:
        return 1, 0
    if po >= wl:
        po = wl - 1
    return wl, po


def savgol_smooth(
    landmarks: np.ndarray,
    confidences: np.ndarray,
    *,
    window_length: int = 7,
    polyorder: int = 2,
    confidence_threshold: float = 0.3,
) -> np.ndarray:
    """Apply Savitzky-Golay smoothing to ``[N,33,3]`` landmarks."""
    arr = _normalize_landmarks(landmarks)
    conf = normalize_confidences(confidences, arr.shape[0])
    masked = apply_confidence_mask(arr, conf, threshold=confidence_threshold)
    wl, po = _normalize_window(arr.shape[0], window_length, polyorder)
    if wl <= 1:
        return np.nan_to_num(masked, nan=0.0).astype(np.float32)

    out = np.empty_like(masked, dtype=np.float32)
    for joint_idx in range(LANDMARK_COUNT):
        for axis_idx in range(3):
            series = interpolate_nans_1d(masked[:, joint_idx, axis_idx])
            filtered = savgol_filter(series, window_length=wl, polyorder=po, mode="interp")
            out[:, joint_idx, axis_idx] = filtered.astype(np.float32)
    return out


def _kalman_1d(
    series: np.ndarray,
    observed_mask: np.ndarray,
    *,
    process_noise: float,
    measurement_noise: float,
) -> np.ndarray:
    n = series.shape[0]
    dt = 1.0
    f = np.array([[1.0, dt], [0.0, 1.0]], dtype=np.float64)
    h = np.array([[1.0, 0.0]], dtype=np.float64)
    q = np.array(
        [[0.25 * dt**4, 0.5 * dt**3], [0.5 * dt**3, dt**2]],
        dtype=np.float64,
    ) * max(process_noise, 1e-9)
    r = np.array([[max(measurement_noise, 1e-9)]], dtype=np.float64)

    x = np.array([float(series[0]), 0.0], dtype=np.float64)
    p = np.eye(2, dtype=np.float64)
    out = np.zeros(n, dtype=np.float64)
    out[0] = x[0]

    for i in range(1, n):
        x = f @ x
        p = f @ p @ f.T + q

        if observed_mask[i]:
            z = np.array([[float(series[i])]], dtype=np.float64)
            y = z - (h @ x).reshape(1, 1)
            s = h @ p @ h.T + r
            k = p @ h.T @ np.linalg.inv(s)
            x = x + (k @ y).reshape(2)
            p = (np.eye(2) - (k @ h)) @ p
        out[i] = x[0]
    return out.astype(np.float32)


def kalman_smooth(
    landmarks: np.ndarray,
    confidences: np.ndarray,
    *,
    confidence_threshold: float = 0.3,
    process_noise: float = 0.01,
    measurement_noise: float = 0.1,
) -> np.ndarray:
    """Apply a constant-velocity Kalman smoother to landmarks."""
    arr = _normalize_landmarks(landmarks)
    conf = normalize_confidences(confidences, arr.shape[0])
    masked = apply_confidence_mask(arr, conf, threshold=confidence_threshold)
    out = np.empty_like(masked, dtype=np.float32)

    for joint_idx in range(LANDMARK_COUNT):
        for axis_idx in range(3):
            raw_series = masked[:, joint_idx, axis_idx]
            observed = ~np.isnan(raw_series)
            series = interpolate_nans_1d(raw_series)
            out[:, joint_idx, axis_idx] = _kalman_1d(
                series,
                observed,
                process_noise=process_noise,
                measurement_noise=measurement_noise,
            )
    return out

