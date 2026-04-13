"""MOTION_CAPTURE_BACKEND factory."""

import pytest

from motion_capture.pose_backend import (
    MediaPipePoseBackend,
    ViTPosePoseBackend,
    create_pose_backend_from_env,
)


def test_create_pose_backend_default_is_mediapipe():
    b = create_pose_backend_from_env()
    assert isinstance(b, MediaPipePoseBackend)
    b.close()


def test_create_pose_backend_vitpose_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTION_CAPTURE_BACKEND", "vitpose")
    with pytest.raises(RuntimeError, match="33 MediaPipe landmarks"):
        create_pose_backend_from_env()


def test_vitpose_backend_reason_is_actionable() -> None:
    assert "pip install -e \".[vitpose]\"" in ViTPosePoseBackend.DEFERRED_REASON
