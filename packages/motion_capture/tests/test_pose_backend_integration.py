from pathlib import Path

import cv2
import pytest

from motion_capture.pose_backend import MediaPipePoseBackend


FIXTURE_IMAGE = Path(__file__).parent / "fixtures" / "pose_test_frame.jpg"


def test_mediapipe_tasks_detects_pose_on_fixture_frame():
    """Run real MediaPipe Tasks inference against a real test frame."""
    if not FIXTURE_IMAGE.exists():
        pytest.skip("Pose fixture image is missing.")

    frame_bgr = cv2.imread(str(FIXTURE_IMAGE))
    if frame_bgr is None:
        pytest.skip("Unable to decode pose fixture image.")
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    backend = MediaPipePoseBackend(prefer_tasks_api=True, auto_download_model=True)
    try:
        if backend.backend_name != "tasks":
            pytest.skip("MediaPipe Tasks backend is unavailable in this environment.")
        result = backend.process_frame(frame_rgb)
    finally:
        backend.close()

    assert result.landmarks is not None
    assert result.landmarks.shape == (33, 3)
    assert result.confidence >= 0.0

