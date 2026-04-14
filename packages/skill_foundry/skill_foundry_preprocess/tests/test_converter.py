from __future__ import annotations

import numpy as np

from skill_foundry_preprocess.converter import (
    PreprocessedLandmarks,
    preprocess_landmarks_payload,
)


def _input_payload() -> dict:
    n = 20
    frames = np.zeros((n, 33, 3), dtype=np.float32)
    for i in range(n):
        frames[i, :, 0] = i * 0.01
        frames[i, :, 1] = np.sin(i * 0.1)
        frames[i, :, 2] = np.cos(i * 0.1)
    return {
        "schema_version": "aurosy_video_landmarks_v1",
        "landmarks": frames.tolist(),
        "confidences": [1.0] * n,
        "timestamps_ms": (np.arange(n, dtype=np.float32) * 33.33).tolist(),
    }


def test_preprocess_landmarks_payload_returns_canonical_schema() -> None:
    result = preprocess_landmarks_payload(
        _input_payload(),
        filter_type="both",
        window_length=5,
        polyorder=2,
        confidence_threshold=0.2,
    )
    assert isinstance(result, PreprocessedLandmarks)
    assert result.schema_version == "aurosy_preprocessed_landmarks_v1"
    assert result.landmarks.shape == (20, 33, 3)
    assert result.confidences.shape == (20, 33)
    assert result.timestamps_ms.shape == (20,)
    assert result.preprocessing_config["filter_type"] == "both"
    assert "jitter_reduction_pct" in result.quality_metrics


def test_roundtrip_dict() -> None:
    result = preprocess_landmarks_payload(_input_payload(), filter_type="savgol")
    restored = PreprocessedLandmarks.from_dict(result.to_dict())
    assert restored.schema_version == result.schema_version
    np.testing.assert_allclose(restored.landmarks, result.landmarks)
    np.testing.assert_allclose(restored.confidences, result.confidences)

