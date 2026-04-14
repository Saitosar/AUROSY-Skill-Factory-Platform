"""Tests for batch pose extractor."""

import numpy as np
import pytest
from pathlib import Path

from skill_foundry_video.pose_extractor import (
    BatchPoseExtractor,
    PoseExtractionResult,
    MEDIAPIPE_LANDMARK_COUNT,
)


class TestPoseExtractionResult:
    def test_to_dict_and_from_dict(self):
        result = PoseExtractionResult(
            landmarks=np.random.rand(10, MEDIAPIPE_LANDMARK_COUNT, 3).astype(np.float32),
            confidences=np.random.rand(10).astype(np.float32),
            timestamps_ms=np.arange(10, dtype=np.float32) * 33.33,
            frame_count=10,
            valid_frame_count=8,
            fps=30.0,
            duration_sec=0.333,
            video_path="/test/video.mp4",
            extraction_config={"target_fps": 30},
        )

        d = result.to_dict()
        restored = PoseExtractionResult.from_dict(d)

        assert restored.frame_count == result.frame_count
        assert restored.valid_frame_count == result.valid_frame_count
        assert restored.fps == result.fps
        np.testing.assert_array_almost_equal(restored.landmarks, result.landmarks)

    def test_confidence_mean(self):
        result = PoseExtractionResult(
            landmarks=np.zeros((5, MEDIAPIPE_LANDMARK_COUNT, 3), dtype=np.float32),
            confidences=np.array([0.9, 0.8, 0.0, 0.7, 0.85], dtype=np.float32),
            timestamps_ms=np.arange(5, dtype=np.float32),
            frame_count=5,
            valid_frame_count=4,
            fps=30.0,
            duration_sec=0.167,
            video_path="",
        )

        mean_conf = result.confidence_mean
        assert 0.8 < mean_conf < 0.9

    def test_missing_frame_ratio(self):
        result = PoseExtractionResult(
            landmarks=np.zeros((10, MEDIAPIPE_LANDMARK_COUNT, 3), dtype=np.float32),
            confidences=np.ones(10, dtype=np.float32),
            timestamps_ms=np.arange(10, dtype=np.float32),
            frame_count=10,
            valid_frame_count=8,
            fps=30.0,
            duration_sec=0.333,
            video_path="",
        )

        assert result.missing_frame_ratio == pytest.approx(0.2)

    def test_save_and_load_json(self, tmp_path):
        result = PoseExtractionResult(
            landmarks=np.random.rand(5, MEDIAPIPE_LANDMARK_COUNT, 3).astype(np.float32),
            confidences=np.random.rand(5).astype(np.float32),
            timestamps_ms=np.arange(5, dtype=np.float32) * 33.33,
            frame_count=5,
            valid_frame_count=5,
            fps=30.0,
            duration_sec=0.167,
            video_path="/test/video.mp4",
        )

        json_path = tmp_path / "landmarks.json"
        result.save_json(json_path)

        assert json_path.exists()

        loaded = PoseExtractionResult.load_json(json_path)
        assert loaded.frame_count == result.frame_count
        np.testing.assert_array_almost_equal(loaded.landmarks, result.landmarks)


class TestBatchPoseExtractor:
    def test_interpolate_missing_frames(self):
        extractor = BatchPoseExtractor()

        frame1 = np.array([[0, 0, 0]] * MEDIAPIPE_LANDMARK_COUNT, dtype=np.float32)
        frame3 = np.array([[2, 2, 2]] * MEDIAPIPE_LANDMARK_COUNT, dtype=np.float32)

        landmarks = [frame1, None, frame3]
        interpolated = extractor._interpolate_missing_frames(landmarks)

        assert interpolated[1] is not None
        expected = np.array([[1, 1, 1]] * MEDIAPIPE_LANDMARK_COUNT, dtype=np.float32)
        np.testing.assert_array_almost_equal(interpolated[1], expected)

    def test_build_landmarks_array(self):
        extractor = BatchPoseExtractor()

        frame1 = np.ones((MEDIAPIPE_LANDMARK_COUNT, 3), dtype=np.float32)
        frame2 = np.ones((MEDIAPIPE_LANDMARK_COUNT, 3), dtype=np.float32) * 2

        landmarks = [frame1, None, frame2]
        array = extractor._build_landmarks_array(landmarks)

        assert array.shape == (3, MEDIAPIPE_LANDMARK_COUNT, 3)
        np.testing.assert_array_equal(array[0], frame1)
        np.testing.assert_array_equal(array[1], np.zeros((MEDIAPIPE_LANDMARK_COUNT, 3)))
        np.testing.assert_array_equal(array[2], frame2)
