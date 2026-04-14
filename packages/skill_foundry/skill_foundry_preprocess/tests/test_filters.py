from __future__ import annotations

import numpy as np

from skill_foundry_preprocess.filters import kalman_smooth, savgol_smooth


def _synthetic_landmarks(n: int = 60) -> tuple[np.ndarray, np.ndarray]:
    t = np.linspace(0, 2.0 * np.pi, n, dtype=np.float32)
    base = np.stack([np.sin(t), np.cos(t), 0.5 * np.sin(0.5 * t)], axis=1)
    landmarks = np.repeat(base[:, np.newaxis, :], 33, axis=1).astype(np.float32)
    rng = np.random.default_rng(123)
    noisy = landmarks + rng.normal(0.0, 0.05, size=landmarks.shape).astype(np.float32)
    confidences = np.ones((n,), dtype=np.float32)
    confidences[10:13] = 0.0
    noisy[10:13, :, :] = 0.0
    return noisy, confidences


def _jitter(landmarks: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(np.diff(landmarks, axis=0), axis=2)))


def test_savgol_smooth_reduces_jitter() -> None:
    noisy, conf = _synthetic_landmarks()
    smoothed = savgol_smooth(
        noisy,
        conf,
        window_length=7,
        polyorder=2,
        confidence_threshold=0.2,
    )
    assert smoothed.shape == noisy.shape
    assert _jitter(smoothed) < _jitter(noisy)


def test_kalman_smooth_fills_low_confidence_gaps() -> None:
    noisy, conf = _synthetic_landmarks()
    smoothed = kalman_smooth(
        noisy,
        conf,
        confidence_threshold=0.5,
        process_noise=0.01,
        measurement_noise=0.1,
    )
    assert smoothed.shape == noisy.shape
    assert np.isfinite(smoothed).all()
    assert _jitter(smoothed) < _jitter(noisy)

