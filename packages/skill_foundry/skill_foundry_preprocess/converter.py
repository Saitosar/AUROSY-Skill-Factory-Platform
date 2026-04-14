"""Input normalization and conversion to AUROSY preprocessed format."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .confidence import LANDMARK_COUNT, normalize_confidences
from .filters import kalman_smooth, savgol_smooth

FilterType = Literal["savgol", "kalman", "both"]


@dataclass
class PreprocessedLandmarks:
    """Canonical AUROSY preprocessed landmarks payload."""

    landmarks: np.ndarray
    confidences: np.ndarray
    timestamps_ms: np.ndarray
    preprocessing_config: dict[str, Any]
    source_format: str
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "aurosy_preprocessed_landmarks_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "landmarks": self.landmarks.tolist(),
            "confidences": self.confidences.tolist(),
            "timestamps_ms": self.timestamps_ms.tolist(),
            "preprocessing_config": self.preprocessing_config,
            "source_format": self.source_format,
            "quality_metrics": self.quality_metrics,
        }

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PreprocessedLandmarks":
        return cls(
            schema_version=str(payload.get("schema_version", "aurosy_preprocessed_landmarks_v1")),
            landmarks=np.asarray(payload["landmarks"], dtype=np.float32),
            confidences=np.asarray(payload["confidences"], dtype=np.float32),
            timestamps_ms=np.asarray(payload["timestamps_ms"], dtype=np.float32),
            preprocessing_config=dict(payload.get("preprocessing_config") or {}),
            source_format=str(payload.get("source_format") or "unknown"),
            quality_metrics=dict(payload.get("quality_metrics") or {}),
        )

    @classmethod
    def load_json(cls, path: Path) -> "PreprocessedLandmarks":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _parse_landmarks_array(payload: Any) -> np.ndarray:
    arr = np.asarray(payload, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[1:] != (LANDMARK_COUNT, 3):
        raise ValueError("landmarks must have shape [N, 33, 3]")
    return arr


def _extract_from_payload(payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    source = str(payload.get("schema_version") or "")
    if source == "aurosy_video_landmarks_v1":
        landmarks = _parse_landmarks_array(payload["landmarks"])
        confidences = normalize_confidences(np.asarray(payload.get("confidences", [])), landmarks.shape[0])
        timestamps = np.asarray(payload.get("timestamps_ms"), dtype=np.float32)
        if timestamps.shape != (landmarks.shape[0],):
            timestamps = np.arange(landmarks.shape[0], dtype=np.float32) * (1000.0 / 30.0)
        return landmarks, confidences, timestamps, source

    if source == "aurosy_capture_v1":
        raw = payload.get("frames") or payload.get("landmarks")
        if raw is None:
            raise ValueError("aurosy_capture_v1 payload requires frames or landmarks")
        landmarks = _parse_landmarks_array(raw)
        conf_raw = payload.get("confidences", np.ones((landmarks.shape[0],), dtype=np.float32))
        confidences = normalize_confidences(np.asarray(conf_raw), landmarks.shape[0])
        timestamps = np.asarray(payload.get("timestamps_ms"), dtype=np.float32)
        if timestamps.shape != (landmarks.shape[0],):
            fps = float(payload.get("fps", 30.0))
            timestamps = np.arange(landmarks.shape[0], dtype=np.float32) * (1000.0 / max(fps, 1e-6))
        return landmarks, confidences, timestamps, source

    if "freemocap_version" in payload:
        raw = payload.get("landmarks") or payload.get("frames") or payload.get("body_3d_xyz")
        if raw is None:
            raise ValueError("freemocap payload requires landmarks/frames/body_3d_xyz")
        landmarks = _parse_landmarks_array(raw)
        conf_raw = payload.get("confidences", np.ones((landmarks.shape[0],), dtype=np.float32))
        confidences = normalize_confidences(np.asarray(conf_raw), landmarks.shape[0])
        timestamps = np.asarray(payload.get("timestamps_ms"), dtype=np.float32)
        if timestamps.shape != (landmarks.shape[0],):
            fps = float(payload.get("fps", 30.0))
            timestamps = np.arange(landmarks.shape[0], dtype=np.float32) * (1000.0 / max(fps, 1e-6))
        return landmarks, confidences, timestamps, "freemocap"

    if "landmarks" in payload:
        landmarks = _parse_landmarks_array(payload["landmarks"])
        conf_raw = payload.get("confidences", np.ones((landmarks.shape[0],), dtype=np.float32))
        confidences = normalize_confidences(np.asarray(conf_raw), landmarks.shape[0])
        timestamps = np.asarray(payload.get("timestamps_ms"), dtype=np.float32)
        if timestamps.shape != (landmarks.shape[0],):
            timestamps = np.arange(landmarks.shape[0], dtype=np.float32) * (1000.0 / 30.0)
        return landmarks, confidences, timestamps, "generic_landmarks"

    raise ValueError("payload does not contain supported landmark fields")


def _jitter_metric(landmarks: np.ndarray) -> float:
    if landmarks.shape[0] < 2:
        return 0.0
    diff = np.diff(landmarks, axis=0)
    return float(np.mean(np.linalg.norm(diff, axis=2)))


def preprocess_landmarks_payload(
    payload: dict[str, Any],
    *,
    filter_type: FilterType = "both",
    window_length: int = 7,
    polyorder: int = 2,
    confidence_threshold: float = 0.3,
    process_noise: float = 0.01,
    measurement_noise: float = 0.1,
) -> PreprocessedLandmarks:
    """Convert payload to canonical format and apply smoothing filters."""
    landmarks, confidences, timestamps_ms, source_format = _extract_from_payload(payload)
    raw_jitter = _jitter_metric(landmarks)

    smoothed = landmarks
    if filter_type in ("savgol", "both"):
        smoothed = savgol_smooth(
            smoothed,
            confidences,
            window_length=window_length,
            polyorder=polyorder,
            confidence_threshold=confidence_threshold,
        )
    if filter_type in ("kalman", "both"):
        smoothed = kalman_smooth(
            smoothed,
            confidences,
            confidence_threshold=confidence_threshold,
            process_noise=process_noise,
            measurement_noise=measurement_noise,
        )
    smoothed = np.asarray(smoothed, dtype=np.float32)

    smoothed_jitter = _jitter_metric(smoothed)
    jitter_reduction_pct = 0.0
    if raw_jitter > 1e-9:
        jitter_reduction_pct = max(0.0, (raw_jitter - smoothed_jitter) / raw_jitter * 100.0)

    low_conf_frames = confidences < float(confidence_threshold)
    metrics = {
        "raw_jitter": raw_jitter,
        "smoothed_jitter": smoothed_jitter,
        "jitter_reduction_pct": jitter_reduction_pct,
        "low_confidence_ratio": float(np.mean(low_conf_frames)),
    }
    config = {
        "filter_type": filter_type,
        "window_length": int(window_length),
        "polyorder": int(polyorder),
        "confidence_threshold": float(confidence_threshold),
        "process_noise": float(process_noise),
        "measurement_noise": float(measurement_noise),
    }
    return PreprocessedLandmarks(
        landmarks=smoothed,
        confidences=confidences.astype(np.float32),
        timestamps_ms=timestamps_ms.astype(np.float32),
        preprocessing_config=config,
        source_format=source_format,
        quality_metrics=metrics,
    )

