"""Pose estimation backends for motion capture."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import ssl
import time
import urllib.request

import numpy as np
import mediapipe as mp

DEFAULT_POSE_LANDMARKER_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)
DEFAULT_MODEL_CACHE_DIR = Path.home() / ".cache" / "aurosy-motion-capture"
MODEL_FILENAME = "pose_landmarker_lite.task"


@dataclass
class PoseResult:
    """Result of pose estimation for a single frame."""

    landmarks: Optional[np.ndarray]
    timestamp_ms: float
    confidence: float = 0.0


class PoseBackend(ABC):
    """Abstract base class for pose estimation backends."""

    @abstractmethod
    def process_frame(self, frame: np.ndarray) -> PoseResult:
        """Process RGB frame and return a pose result."""

    @abstractmethod
    def close(self) -> None:
        """Release backend resources."""


class MediaPipePoseBackend(PoseBackend):
    """MediaPipe Pose backend - CPU-friendly, works without GPU."""

    LANDMARK_COUNT = 33

    def __init__(
        self,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        prefer_tasks_api: bool = True,
        auto_download_model: bool = True,
        model_path: Optional[str] = None,
    ) -> None:
        self._pose = None
        self._backend_available = False
        self._backend_name = "unavailable"
        self._model_complexity = model_complexity
        self._min_detection_confidence = min_detection_confidence
        self._min_tracking_confidence = min_tracking_confidence
        self._prefer_tasks_api = prefer_tasks_api
        self._auto_download_model = auto_download_model
        self._explicit_model_path = Path(model_path).expanduser() if model_path else None
        self._init_backend()

    def _init_backend(self) -> None:
        """Initialize whichever MediaPipe API is available in runtime."""
        if self._prefer_tasks_api and self._init_tasks_backend():
            return

        mp_solutions = getattr(mp, "solutions", None)
        if mp_solutions is None:
            return
        mp_pose = getattr(mp_solutions, "pose", None)
        if mp_pose is None:
            return

        self._pose = mp_pose.Pose(
            model_complexity=self._model_complexity,
            min_detection_confidence=self._min_detection_confidence,
            min_tracking_confidence=self._min_tracking_confidence,
        )
        self._backend_available = True
        self._backend_name = "solutions"

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def _resolve_model_path(self) -> Optional[Path]:
        if self._explicit_model_path:
            return self._explicit_model_path if self._explicit_model_path.exists() else None

        env_path = os.getenv("MOTION_CAPTURE_MEDIAPIPE_MODEL_PATH")
        if env_path:
            candidate = Path(env_path).expanduser()
            if candidate.exists():
                return candidate
            return None

        cache_dir = Path(
            os.getenv("MOTION_CAPTURE_MEDIAPIPE_CACHE_DIR", str(DEFAULT_MODEL_CACHE_DIR))
        ).expanduser()
        model_file = cache_dir / MODEL_FILENAME
        if model_file.exists():
            return model_file
        if not self._auto_download_model:
            return None

        model_url = os.getenv(
            "MOTION_CAPTURE_MEDIAPIPE_MODEL_URL", DEFAULT_POSE_LANDMARKER_MODEL_URL
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        ssl_context = None
        try:
            import certifi

            ssl_context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ssl_context = ssl.create_default_context()

        with urllib.request.urlopen(model_url, timeout=30, context=ssl_context) as response:
            model_file.write_bytes(response.read())
        return model_file

    def _init_tasks_backend(self) -> bool:
        try:
            from mediapipe.tasks.python.core.base_options import BaseOptions
            from mediapipe.tasks.python.vision.pose_landmarker import (
                PoseLandmarker,
                PoseLandmarkerOptions,
            )
        except Exception:
            return False

        try:
            model_file = self._resolve_model_path()
            if model_file is None:
                return False

            options = PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_file)),
                min_pose_detection_confidence=self._min_detection_confidence,
                min_tracking_confidence=self._min_tracking_confidence,
            )
            self._pose = PoseLandmarker.create_from_options(options)
            self._backend_available = True
            self._backend_name = "tasks"
            return True
        except Exception:
            return False

    def process_frame(self, frame: np.ndarray) -> PoseResult:
        timestamp_ms = time.time() * 1000.0
        if not self._backend_available or self._pose is None:
            return PoseResult(landmarks=None, timestamp_ms=timestamp_ms, confidence=0.0)
        if self._backend_name == "tasks":
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            result = self._pose.detect(mp_image)
            if not result.pose_landmarks:
                return PoseResult(landmarks=None, timestamp_ms=timestamp_ms, confidence=0.0)

            first_pose = result.pose_landmarks[0]
            landmarks = np.array([[lm.x, lm.y, lm.z] for lm in first_pose], dtype=np.float32)
            visibilities = [getattr(lm, "visibility", 1.0) for lm in first_pose]
            avg_visibility = float(np.mean(visibilities)) if visibilities else 0.0
            return PoseResult(
                landmarks=landmarks,
                timestamp_ms=timestamp_ms,
                confidence=avg_visibility,
            )

        results = self._pose.process(frame)
        if results.pose_landmarks is None:
            return PoseResult(landmarks=None, timestamp_ms=timestamp_ms, confidence=0.0)

        landmarks = np.array(
            [[lm.x, lm.y, lm.z] for lm in results.pose_landmarks.landmark],
            dtype=np.float32,
        )
        avg_visibility = float(
            np.mean([lm.visibility for lm in results.pose_landmarks.landmark])
        )
        return PoseResult(
            landmarks=landmarks,
            timestamp_ms=timestamp_ms,
            confidence=avg_visibility,
        )

    def close(self) -> None:
        if self._pose is not None:
            self._pose.close()


def create_pose_backend_from_env() -> PoseBackend:
    """
    Select pose backend from ``MOTION_CAPTURE_BACKEND`` (default: ``mediapipe``).

    ``vitpose`` is reserved for a future mmpose/ViTPose integration (GPU, optional extras);
    selecting it currently raises ``RuntimeError`` at startup with setup instructions.
    """
    name = os.environ.get("MOTION_CAPTURE_BACKEND", "mediapipe").strip().lower()
    if name == "vitpose":
        raise RuntimeError(
            "MOTION_CAPTURE_BACKEND=vitpose is not implemented yet. "
            "Use mediapipe (default), or install optional deps and implement ViTPosePoseBackend — "
            "see packages/motion_capture/README.md."
        )
    if name not in ("mediapipe", ""):
        # Unknown value: stay on MediaPipe but make misconfiguration visible in logs.
        import logging

        logging.getLogger(__name__).warning(
            "Unknown MOTION_CAPTURE_BACKEND=%r; using mediapipe.",
            name,
        )
    return MediaPipePoseBackend()

