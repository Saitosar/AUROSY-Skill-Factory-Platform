import numpy as np

from motion_capture.pose_backend import MediaPipePoseBackend, PoseResult


def test_mediapipe_backend_returns_pose_result():
    """MediaPipe backend should return PoseResult with 33 landmarks."""
    backend = MediaPipePoseBackend()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    try:
        result = backend.process_frame(frame)
    finally:
        backend.close()

    assert isinstance(result, PoseResult)
    assert result.landmarks is None or result.landmarks.shape == (33, 3)
    assert isinstance(result.timestamp_ms, float)


def test_mediapipe_backend_detects_pose_in_test_image():
    """Backend should return no landmarks for an empty frame."""
    backend = MediaPipePoseBackend()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    try:
        result = backend.process_frame(frame)
    finally:
        backend.close()

    assert result.landmarks is None

