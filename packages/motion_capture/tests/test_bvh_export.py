import numpy as np
import pytest

from motion_capture.bvh_export import BVHExporter, RecordingSession


def test_bvh_exporter_creates_valid_bvh():
    """BVH exporter should create valid BVH string from landmarks."""
    session = RecordingSession(fps=30.0)

    for i in range(3):
        landmarks = np.random.rand(33, 3).astype(np.float32)
        session.add_frame(landmarks, timestamp_ms=i * 33.33)

    exporter = BVHExporter()
    bvh_content = exporter.export(session)

    assert isinstance(bvh_content, str)
    assert "HIERARCHY" in bvh_content
    assert "MOTION" in bvh_content
    assert "Frames: 3" in bvh_content


def test_recording_session_tracks_duration():
    """RecordingSession should track total duration."""
    session = RecordingSession(fps=30.0)
    session.add_frame(np.zeros((33, 3)), timestamp_ms=0.0)
    session.add_frame(np.zeros((33, 3)), timestamp_ms=1000.0)

    assert session.duration_sec == pytest.approx(1.0, rel=0.01)
    assert session.frame_count == 2

