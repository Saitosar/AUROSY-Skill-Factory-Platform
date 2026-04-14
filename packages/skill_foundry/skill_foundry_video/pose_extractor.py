"""Batch pose extraction from video files using MediaPipe."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_TARGET_FPS = 30
MEDIAPIPE_LANDMARK_COUNT = 33


@dataclass
class PoseExtractionResult:
    """Result of pose extraction from video."""

    landmarks: np.ndarray
    confidences: np.ndarray
    timestamps_ms: np.ndarray
    frame_count: int
    valid_frame_count: int
    fps: float
    duration_sec: float
    video_path: str
    extraction_config: dict[str, Any] = field(default_factory=dict)

    @property
    def confidence_mean(self) -> float:
        if self.valid_frame_count == 0:
            return 0.0
        valid_mask = self.confidences > 0
        return float(np.mean(self.confidences[valid_mask])) if np.any(valid_mask) else 0.0

    @property
    def missing_frame_ratio(self) -> float:
        if self.frame_count == 0:
            return 1.0
        return 1.0 - (self.valid_frame_count / self.frame_count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "aurosy_video_landmarks_v1",
            "landmarks": self.landmarks.tolist(),
            "confidences": self.confidences.tolist(),
            "timestamps_ms": self.timestamps_ms.tolist(),
            "frame_count": self.frame_count,
            "valid_frame_count": self.valid_frame_count,
            "fps": self.fps,
            "duration_sec": self.duration_sec,
            "confidence_mean": self.confidence_mean,
            "missing_frame_ratio": self.missing_frame_ratio,
            "video_path": self.video_path,
            "extraction_config": self.extraction_config,
        }

    def save_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PoseExtractionResult:
        return cls(
            landmarks=np.array(data["landmarks"], dtype=np.float32),
            confidences=np.array(data["confidences"], dtype=np.float32),
            timestamps_ms=np.array(data["timestamps_ms"], dtype=np.float32),
            frame_count=data["frame_count"],
            valid_frame_count=data["valid_frame_count"],
            fps=data["fps"],
            duration_sec=data["duration_sec"],
            video_path=data.get("video_path", ""),
            extraction_config=data.get("extraction_config", {}),
        )

    @classmethod
    def load_json(cls, path: Path) -> PoseExtractionResult:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


class BatchPoseExtractor:
    """Extract poses from video frames in batch."""

    def __init__(
        self,
        target_fps: float = DEFAULT_TARGET_FPS,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        interpolate_missing: bool = True,
    ):
        self.target_fps = target_fps
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.interpolate_missing = interpolate_missing
        self._pose = None

    def _init_mediapipe(self):
        """Lazy initialization of MediaPipe."""
        if self._pose is not None:
            return

        try:
            import mediapipe as mp
            self._mp_pose = mp.solutions.pose
            self._pose = self._mp_pose.Pose(
                model_complexity=1,
                min_detection_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence,
            )
        except ImportError as e:
            raise RuntimeError(
                "MediaPipe not installed. Install with: pip install mediapipe"
            ) from e

    def extract(
        self,
        video_path: Path | str,
        *,
        start_sec: float | None = None,
        end_sec: float | None = None,
    ) -> PoseExtractionResult:
        """Extract poses from video file.

        Args:
            video_path: Path to video file
            start_sec: Optional start time
            end_sec: Optional end time

        Returns:
            PoseExtractionResult with extracted landmarks
        """
        self._init_mediapipe()
        video_path = Path(video_path)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        try:
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / source_fps if source_fps > 0 else 0

            if start_sec is not None:
                start_frame = int(start_sec * source_fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            else:
                start_sec = 0.0
                start_frame = 0

            if end_sec is not None:
                end_frame = int(end_sec * source_fps)
            else:
                end_sec = duration
                end_frame = total_frames

            frame_interval = max(1, int(source_fps / self.target_fps))
            expected_frames = int((end_frame - start_frame) / frame_interval)

            landmarks_list: list[np.ndarray | None] = []
            confidences_list: list[float] = []
            timestamps_list: list[float] = []

            frame_idx = start_frame
            processed = 0

            while frame_idx < end_frame:
                ret, frame = cap.read()
                if not ret:
                    break

                if (frame_idx - start_frame) % frame_interval == 0:
                    timestamp_ms = (frame_idx / source_fps) * 1000
                    landmarks, confidence = self._process_frame(frame)

                    landmarks_list.append(landmarks)
                    confidences_list.append(confidence)
                    timestamps_list.append(timestamp_ms)
                    processed += 1

                    if processed % 100 == 0:
                        logger.info("Processed %d frames...", processed)

                frame_idx += 1

            if self.interpolate_missing:
                landmarks_list = self._interpolate_missing_frames(landmarks_list)

            landmarks_array = self._build_landmarks_array(landmarks_list)
            confidences_array = np.array(confidences_list, dtype=np.float32)
            timestamps_array = np.array(timestamps_list, dtype=np.float32)

            valid_count = sum(1 for c in confidences_list if c > 0)

            return PoseExtractionResult(
                landmarks=landmarks_array,
                confidences=confidences_array,
                timestamps_ms=timestamps_array,
                frame_count=len(landmarks_list),
                valid_frame_count=valid_count,
                fps=self.target_fps,
                duration_sec=end_sec - start_sec,
                video_path=str(video_path),
                extraction_config={
                    "target_fps": self.target_fps,
                    "min_detection_confidence": self.min_detection_confidence,
                    "min_tracking_confidence": self.min_tracking_confidence,
                    "interpolate_missing": self.interpolate_missing,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                },
            )
        finally:
            cap.release()

    def _process_frame(self, frame: np.ndarray) -> tuple[np.ndarray | None, float]:
        """Process single frame and extract pose landmarks."""
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._pose.process(frame_rgb)

        if results.pose_landmarks is None:
            return None, 0.0

        landmarks = np.array(
            [[lm.x, lm.y, lm.z] for lm in results.pose_landmarks.landmark],
            dtype=np.float32,
        )

        avg_visibility = np.mean(
            [lm.visibility for lm in results.pose_landmarks.landmark]
        )

        return landmarks, float(avg_visibility)

    def _interpolate_missing_frames(
        self, landmarks_list: list[np.ndarray | None]
    ) -> list[np.ndarray | None]:
        """Interpolate missing frames using linear interpolation."""
        if not landmarks_list:
            return landmarks_list

        result = landmarks_list.copy()
        n = len(result)

        valid_indices = [i for i, lm in enumerate(result) if lm is not None]

        if len(valid_indices) < 2:
            return result

        for i in range(n):
            if result[i] is not None:
                continue

            prev_idx = None
            next_idx = None

            for vi in valid_indices:
                if vi < i:
                    prev_idx = vi
                elif vi > i and next_idx is None:
                    next_idx = vi
                    break

            if prev_idx is not None and next_idx is not None:
                alpha = (i - prev_idx) / (next_idx - prev_idx)
                result[i] = (
                    (1 - alpha) * result[prev_idx] + alpha * result[next_idx]
                )
            elif prev_idx is not None:
                result[i] = result[prev_idx].copy()
            elif next_idx is not None:
                result[i] = result[next_idx].copy()

        return result

    def _build_landmarks_array(
        self, landmarks_list: list[np.ndarray | None]
    ) -> np.ndarray:
        """Build final landmarks array with shape [N, 33, 3]."""
        n = len(landmarks_list)
        result = np.zeros((n, MEDIAPIPE_LANDMARK_COUNT, 3), dtype=np.float32)

        for i, lm in enumerate(landmarks_list):
            if lm is not None and lm.shape == (MEDIAPIPE_LANDMARK_COUNT, 3):
                result[i] = lm

        return result

    def close(self) -> None:
        """Release MediaPipe resources."""
        if self._pose is not None:
            self._pose.close()
            self._pose = None


def extract_poses_from_video(
    video_path: Path | str,
    *,
    target_fps: float = DEFAULT_TARGET_FPS,
    start_sec: float | None = None,
    end_sec: float | None = None,
    min_detection_confidence: float = 0.5,
    interpolate_missing: bool = True,
) -> PoseExtractionResult:
    """Convenience function to extract poses from video.

    Args:
        video_path: Path to video file
        target_fps: Target frames per second for extraction
        start_sec: Optional start time
        end_sec: Optional end time
        min_detection_confidence: MediaPipe detection confidence threshold
        interpolate_missing: Whether to interpolate missing frames

    Returns:
        PoseExtractionResult with extracted landmarks
    """
    extractor = BatchPoseExtractor(
        target_fps=target_fps,
        min_detection_confidence=min_detection_confidence,
        interpolate_missing=interpolate_missing,
    )
    try:
        return extractor.extract(video_path, start_sec=start_sec, end_sec=end_sec)
    finally:
        extractor.close()


def main() -> None:
    """CLI entry point for pose extraction."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract poses from video")
    parser.add_argument("video", type=Path, help="Video file path")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON path")
    parser.add_argument("--fps", type=float, default=DEFAULT_TARGET_FPS, help="Target FPS")
    parser.add_argument("--start", type=float, help="Start time in seconds")
    parser.add_argument("--end", type=float, help="End time in seconds")
    parser.add_argument("--no-interpolate", action="store_true", help="Disable interpolation")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    result = extract_poses_from_video(
        args.video,
        target_fps=args.fps,
        start_sec=args.start,
        end_sec=args.end,
        interpolate_missing=not args.no_interpolate,
    )

    output_path = args.output or args.video.with_suffix(".landmarks.json")
    result.save_json(output_path)

    print(f"Extracted {result.valid_frame_count}/{result.frame_count} frames")
    print(f"Mean confidence: {result.confidence_mean:.2%}")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
