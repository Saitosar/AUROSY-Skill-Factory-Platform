from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

TEST_FILE = Path(__file__).resolve()
BACKEND_ROOT = TEST_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app  # noqa: E402


def _frame_payload() -> list[list[float]]:
    frame: list[list[float]] = []
    for idx in range(33):
        frame.append([idx * 0.01, idx * 0.02, idx * 0.03])
    return frame


class TestRetargetApi(unittest.TestCase):
    def test_retarget_single_frame_returns_flat_angles(self) -> None:
        client = TestClient(create_app())
        body = {"landmarks": _frame_payload()}
        response = client.post("/api/pipeline/retarget", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["frame_count"], 1)
        self.assertEqual(len(payload["joint_order"]), 29)
        self.assertEqual(len(payload["joint_angles_rad"]), 29)

    def test_retarget_sequence_returns_matrix(self) -> None:
        client = TestClient(create_app())
        frame = _frame_payload()
        body = {"landmarks": [frame, frame]}
        response = client.post("/api/pipeline/retarget", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["frame_count"], 2)
        self.assertEqual(len(payload["joint_angles_rad"]), 2)
        self.assertEqual(len(payload["joint_angles_rad"][0]), 29)

    def test_retarget_invalid_shape_is_422(self) -> None:
        client = TestClient(create_app())
        body = {"landmarks": [[0.0, 0.0, 0.0]]}
        response = client.post("/api/pipeline/retarget", json=body)
        self.assertEqual(response.status_code, 422)

    def test_retarget_unsupported_source_is_400(self) -> None:
        client = TestClient(create_app())
        body = {
            "landmarks": _frame_payload(),
            "source_skeleton": "unknown_source",
        }
        response = client.post("/api/pipeline/retarget", json=body)
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
