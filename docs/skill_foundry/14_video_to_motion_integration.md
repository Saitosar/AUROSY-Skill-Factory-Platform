# Video-to-Motion Integration: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable users to record human motion via webcam, preview it on G1 robot model in real-time, and train RL policies that imitate the captured motion using AMP (Adversarial Motion Priors).

**Architecture:** Six-layer integration extending existing Skill Foundry pipeline. Motion Capture Service (new microservice) → Retargeting Engine (new module in skill_foundry) → MuJoCo Browser Live Track (frontend extension) → AMP RL Training (`skill_foundry_rl/amp_train.py`, CLI `skill-foundry-train --mode amp`) → Extended Eval/Export → Motion Skill Bundle.

**Tech Stack:** Python (FastAPI, MediaPipe/ViTPose, MuJoCo), TypeScript/React (frontend), WebSocket streaming, BVH format, AMP/DeepMimic RL.

**Repositories:**
- **Backend/Platform:** `AUROSY_creators_factory_platform` (`packages/skill_foundry/`, `web/backend/`, `docker/`)
- **Frontend:** `AUROSY_creators_factory` (`web/frontend/`)

---

## Table of Contents

| Phase | Description | Dependencies |
|-------|-------------|--------------|
| **Phase 1** | Motion Capture Service (isolated microservice) | None |
| **Phase 2** | Retargeting Engine (human→G1 mapping) | Phase 1 |
| **Phase 3** | Frontend: Camera UI + Live Track | Phase 1, Phase 2 |
| **Phase 4** | AMP RL Training Pipeline | Phase 2 |
| **Phase 5** | Eval & Export Extensions | Phase 4 |
| **Phase 6** | Motion Skill Bundle & End-to-End Flow | Phase 3, Phase 5 |

---

## Phase 1: Motion Capture Service

**Objective:** Create a standalone Python microservice that accepts video stream from browser and returns joint coordinates in real-time via WebSocket, plus BVH file on session completion.

**Location:** `packages/motion_capture/` (new package in platform repo)

### Task 1.1: Package Scaffold

**Files:**
- Create: `packages/motion_capture/__init__.py`
- Create: `packages/motion_capture/pyproject.toml`
- Create: `packages/motion_capture/README.md`

- [ ] **Step 1: Create package directory structure**

```bash
mkdir -p packages/motion_capture/motion_capture
mkdir -p packages/motion_capture/tests
```

- [ ] **Step 2: Create pyproject.toml**

```toml
# packages/motion_capture/pyproject.toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "aurosy-motion-capture"
version = "0.1.0"
description = "Motion capture service for AUROSY Skill Factory"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "websockets>=12.0",
    "mediapipe>=0.10.9",
    "numpy>=1.24.0",
    "opencv-python>=4.8.0",
]

[project.optional-dependencies]
vitpose = ["mmpose>=1.3.0", "mmcv>=2.1.0", "torch>=2.0.0"]
dev = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0"]

[project.scripts]
motion-capture-server = "motion_capture.server:main"

[tool.setuptools.packages.find]
where = ["."]
```

- [ ] **Step 3: Create __init__.py**

```python
# packages/motion_capture/motion_capture/__init__.py
"""AUROSY Motion Capture Service - video to skeleton coordinates."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Commit scaffold**

```bash
git add packages/motion_capture/
git commit -m "feat(motion-capture): scaffold package structure"
```

---

### Task 1.2: Pose Estimation Backend (MediaPipe)

**Files:**
- Create: `packages/motion_capture/motion_capture/pose_backend.py`
- Create: `packages/motion_capture/tests/test_pose_backend.py`

- [ ] **Step 1: Write failing test for pose extraction**

```python
# packages/motion_capture/tests/test_pose_backend.py
import numpy as np
import pytest
from motion_capture.pose_backend import MediaPipePoseBackend, PoseResult

def test_mediapipe_backend_returns_pose_result():
    """MediaPipe backend should return PoseResult with 33 landmarks."""
    backend = MediaPipePoseBackend()
    # Create a dummy 480x640 RGB frame (black image)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = backend.process_frame(frame)
    
    assert isinstance(result, PoseResult)
    assert result.landmarks is None or result.landmarks.shape == (33, 3)
    assert isinstance(result.timestamp_ms, float)

def test_mediapipe_backend_detects_pose_in_test_image():
    """Backend should detect pose when person is visible."""
    backend = MediaPipePoseBackend()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = backend.process_frame(frame)
    assert result.landmarks is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/motion_capture
pytest tests/test_pose_backend.py -v
```

Expected: FAIL with "No module named 'motion_capture.pose_backend'"

- [ ] **Step 3: Implement MediaPipe pose backend**

```python
# packages/motion_capture/motion_capture/pose_backend.py
"""Pose estimation backends for motion capture."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import time

import numpy as np
import mediapipe as mp


@dataclass
class PoseResult:
    """Result of pose estimation for a single frame."""
    landmarks: Optional[np.ndarray]  # Shape: (33, 3) for MediaPipe
    timestamp_ms: float
    confidence: float = 0.0


class PoseBackend(ABC):
    """Abstract base class for pose estimation backends."""
    
    @abstractmethod
    def process_frame(self, frame: np.ndarray) -> PoseResult:
        """Process a single BGR/RGB frame and return pose landmarks."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Release resources."""
        pass


class MediaPipePoseBackend(PoseBackend):
    """MediaPipe Pose backend - CPU-friendly, works without GPU."""
    
    LANDMARK_COUNT = 33
    
    def __init__(
        self,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        self._mp_pose = mp.solutions.pose
        self._pose = self._mp_pose.Pose(
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
    
    def process_frame(self, frame: np.ndarray) -> PoseResult:
        timestamp_ms = time.time() * 1000
        results = self._pose.process(frame)
        
        if results.pose_landmarks is None:
            return PoseResult(landmarks=None, timestamp_ms=timestamp_ms, confidence=0.0)
        
        landmarks = np.array([
            [lm.x, lm.y, lm.z] for lm in results.pose_landmarks.landmark
        ], dtype=np.float32)
        
        avg_visibility = np.mean([lm.visibility for lm in results.pose_landmarks.landmark])
        
        return PoseResult(landmarks=landmarks, timestamp_ms=timestamp_ms, confidence=float(avg_visibility))
    
    def close(self) -> None:
        self._pose.close()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd packages/motion_capture
pip install -e ".[dev]"
pytest tests/test_pose_backend.py -v
```

Expected: PASS

- [ ] **Step 5: Commit implementation**

```bash
git add packages/motion_capture/
git commit -m "feat(motion-capture): implement MediaPipe pose backend"
```

---

### Task 1.3: BVH Exporter

**Files:**
- Create: `packages/motion_capture/motion_capture/bvh_export.py`
- Create: `packages/motion_capture/tests/test_bvh_export.py`

- [ ] **Step 1: Write failing test for BVH export**

```python
# packages/motion_capture/tests/test_bvh_export.py
import numpy as np
import pytest
from motion_capture.bvh_export import BVHExporter, RecordingSession

def test_bvh_exporter_creates_valid_bvh():
    """BVH exporter should create valid BVH string from landmarks."""
    session = RecordingSession(fps=30.0)
    
    # Add 3 frames of dummy landmarks (33 points each)
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
```

- [ ] **Step 2: Implement BVH exporter**

```python
# packages/motion_capture/motion_capture/bvh_export.py
"""BVH format export for recorded motion capture sessions."""

from dataclasses import dataclass, field
from typing import List, Tuple
import numpy as np


@dataclass
class RecordingSession:
    """Accumulates pose frames during a recording session."""
    
    fps: float = 30.0
    frames: List[Tuple[np.ndarray, float]] = field(default_factory=list)
    
    def add_frame(self, landmarks: np.ndarray, timestamp_ms: float) -> None:
        """Add a frame with landmarks and timestamp."""
        self.frames.append((landmarks.copy(), timestamp_ms))
    
    @property
    def frame_count(self) -> int:
        return len(self.frames)
    
    @property
    def duration_sec(self) -> float:
        if len(self.frames) < 2:
            return 0.0
        return (self.frames[-1][1] - self.frames[0][1]) / 1000.0
    
    def clear(self) -> None:
        self.frames.clear()


MEDIAPIPE_SKELETON = {
    "Hips": 23, "Spine": 11, "Neck": 0, "Head": 0,
    "LeftShoulder": 11, "LeftArm": 13, "LeftForeArm": 15, "LeftHand": 17,
    "RightShoulder": 12, "RightArm": 14, "RightForeArm": 16, "RightHand": 18,
    "LeftUpLeg": 23, "LeftLeg": 25, "LeftFoot": 27,
    "RightUpLeg": 24, "RightLeg": 26, "RightFoot": 28,
}


class BVHExporter:
    """Export RecordingSession to BVH format."""
    
    def __init__(self, scale: float = 100.0):
        self.scale = scale
    
    def export(self, session: RecordingSession) -> str:
        lines = []
        lines.append("HIERARCHY")
        lines.append("ROOT Hips")
        lines.append("{")
        lines.append("  OFFSET 0.0 0.0 0.0")
        lines.append("  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation")
        self._add_joint(lines, "Spine", 2)
        self._add_joint(lines, "LeftUpLeg", 2)
        self._add_joint(lines, "RightUpLeg", 2)
        lines.append("}")
        
        lines.append("MOTION")
        lines.append(f"Frames: {session.frame_count}")
        frame_time = 1.0 / session.fps if session.fps > 0 else 0.033
        lines.append(f"Frame Time: {frame_time:.6f}")
        
        # Frame data
        for landmarks, _ in session.frames:
            frame_data = self._landmarks_to_frame_data(landmarks)
            lines.append(" ".join(f"{v:.4f}" for v in frame_data))
        
        return "\n".join(lines)
    
    def _add_joint(self, lines: List[str], name: str, indent: int) -> None:
        prefix = "  " * indent
        lines.extend([
            f"{prefix}JOINT {name}", f"{prefix}{{",
            f"{prefix}  OFFSET 0.0 10.0 0.0",
            f"{prefix}  CHANNELS 3 Zrotation Xrotation Yrotation",
            f"{prefix}  End Site", f"{prefix}  {{",
            f"{prefix}    OFFSET 0.0 10.0 0.0",
            f"{prefix}  }}", f"{prefix}}}"
        ])
    
    def _landmarks_to_frame_data(self, landmarks: np.ndarray) -> List[float]:
        hip_idx = MEDIAPIPE_SKELETON["Hips"]
        root_pos = landmarks[hip_idx] * self.scale
        return [root_pos[0], root_pos[1], root_pos[2], 0.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
```

- [ ] **Step 3: Commit implementation**

```bash
git add packages/motion_capture/
git commit -m "feat(motion-capture): implement BVH exporter"
```

---

### Task 1.4: WebSocket Server

**Files:**
- Create: `packages/motion_capture/motion_capture/server.py`
- Create: `packages/motion_capture/tests/test_server.py`

- [ ] **Step 1: Write failing test for WebSocket endpoint**

```python
# packages/motion_capture/tests/test_server.py
import pytest
from fastapi.testclient import TestClient
from motion_capture.server import create_app

def test_health_endpoint():
    """Health endpoint should return status ok."""
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_websocket_connection():
    """WebSocket should accept connection and respond to ping."""
    app = create_app()
    client = TestClient(app)
    with client.websocket_connect("/ws/capture") as websocket:
        websocket.send_json({"type": "ping"})
        data = websocket.receive_json()
        assert data["type"] == "pong"
```

- [ ] **Step 2: Implement WebSocket server**

```python
# packages/motion_capture/motion_capture/server.py
"""Motion Capture WebSocket server."""

import asyncio
import base64
import json
import logging
from typing import Dict, Optional

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .pose_backend import MediaPipePoseBackend, PoseBackend
from .bvh_export import BVHExporter, RecordingSession

logger = logging.getLogger(__name__)


class CaptureSession:
    """Manages a single capture session for a WebSocket connection."""
    
    def __init__(self, backend: PoseBackend):
        self.backend = backend
        self.recording = RecordingSession(fps=30.0)
        self.is_recording = False
        self.exporter = BVHExporter()
    
    def process_frame(self, frame_data: bytes) -> Optional[Dict]:
        """Process a single frame from the client.
        
        Args:
            frame_data: JPEG-encoded frame bytes
            
        Returns:
            Dict with landmarks if detected, None otherwise
        """
        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.backend.process_frame(frame_rgb)
        
        if result.landmarks is not None and self.is_recording:
            self.recording.add_frame(result.landmarks, result.timestamp_ms)
        
        if result.landmarks is None:
            return None
        
        return {
            "type": "pose",
            "landmarks": result.landmarks.tolist(),
            "confidence": result.confidence,
            "timestamp_ms": result.timestamp_ms,
        }
    
    def start_recording(self) -> None:
        self.recording.clear()
        self.is_recording = True
    
    def stop_recording(self) -> str:
        self.is_recording = False
        return self.exporter.export(self.recording)


def create_app() -> FastAPI:
    app = FastAPI(title="AUROSY Motion Capture Service")
    
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "motion-capture"}
    
    @app.websocket("/ws/capture")
    async def websocket_capture(websocket: WebSocket):
        await websocket.accept()
        backend = MediaPipePoseBackend()
        session = CaptureSession(backend)
        
        try:
            while True:
                message = await websocket.receive()
                
                if "text" in message:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif msg_type == "start_recording":
                        session.start_recording()
                        await websocket.send_json({"type": "recording_started"})
                    elif msg_type == "stop_recording":
                        bvh_content = session.stop_recording()
                        await websocket.send_json({
                            "type": "recording_stopped", "bvh": bvh_content,
                            "duration_sec": session.recording.duration_sec,
                            "frame_count": session.recording.frame_count,
                        })
                
                elif "bytes" in message:
                    result = session.process_frame(message["bytes"])
                    if result:
                        await websocket.send_json(result)
        
        except WebSocketDisconnect:
            logger.info("Client disconnected")
        finally:
            backend.close()
    
    return app


def main():
    """Entry point for motion-capture-server command."""
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit implementation**

```bash
git add packages/motion_capture/
git commit -m "feat(motion-capture): implement WebSocket server"
```

---

### Task 1.5: Docker Container

**Files:**
- Create: `docker/motion_capture/Dockerfile`
- Create: `docker/motion_capture/README.md`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# docker/motion_capture/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY packages/motion_capture /app/packages/motion_capture
RUN pip install --no-cache-dir /app/packages/motion_capture

EXPOSE 8001
ENTRYPOINT ["motion-capture-server"]
```

- [ ] **Step 2: Commit Docker setup**

```bash
git add docker/motion_capture/
git commit -m "feat(motion-capture): add Docker container"
```

---

## Phase 2: Retargeting Engine

**Objective:** Create a module that maps human skeleton (MediaPipe 33 landmarks) to G1 robot joint angles, respecting kinematic constraints.

**Location:** `packages/skill_foundry/skill_foundry_retarget/` (new subpackage)

### Implementation status (current)

- `skill_foundry_retarget` package is implemented in `packages/skill_foundry/skill_foundry_retarget/`.
- Joint mapping is versioned in `packages/skill_foundry/skill_foundry_validation/models/g1_description/joint_map.json`.
- Backend API integration is available at `POST /api/pipeline/retarget` (`web/backend/app/main.py` + `web/backend/app/services/retargeting.py`).
- `GET /api/meta` exposes retargeting capability fields: `retargeting_enabled`, `retargeting_source_skeleton`, `retargeting_target_robot`.

### Task 2.1: Joint Mapping Configuration

**Files:**
- Create: `packages/skill_foundry/skill_foundry_retarget/__init__.py`
- Create: `packages/skill_foundry/skill_foundry_retarget/joint_map.py`
- Create: `packages/skill_foundry/skill_foundry_validation/models/g1_description/joint_map.json`

- [ ] **Step 1: Create joint_map.json configuration**

```json
{
  "version": "1.0",
  "source_skeleton": "mediapipe_pose_33",
  "target_robot": "unitree_g1_29dof",
  "mappings": {
    "left_hip_yaw": {"source_landmarks": [23, 25], "computation": "angle_between_vectors", "reference_axis": [0, 0, 1], "scale": 1.0, "limits": [-0.43, 0.43]},
    "left_hip_roll": {"source_landmarks": [23, 24, 25], "computation": "plane_angle", "scale": 1.0, "limits": [-0.43, 0.43]},
    "left_hip_pitch": {"source_landmarks": [11, 23, 25], "computation": "angle_3points", "offset": -1.57, "scale": 1.0, "limits": [-2.53, 2.53]},
    "left_knee": {"source_landmarks": [23, 25, 27], "computation": "angle_3points", "offset": 0.0, "scale": 1.0, "limits": [-0.26, 2.05]},
    "left_ankle_pitch": {"source_landmarks": [25, 27, 31], "computation": "angle_3points", "scale": 0.5, "limits": [-0.87, 0.52]},
    "left_ankle_roll": {"source_landmarks": [27, 29, 31], "computation": "angle_3points", "scale": 0.5, "limits": [-0.26, 0.26]},
    "right_hip_yaw": {"source_landmarks": [24, 26], "computation": "angle_between_vectors", "reference_axis": [0, 0, 1], "scale": 1.0, "limits": [-0.43, 0.43]},
    "right_hip_roll": {"source_landmarks": [23, 24, 26], "computation": "plane_angle", "scale": 1.0, "limits": [-0.43, 0.43]},
    "right_hip_pitch": {"source_landmarks": [12, 24, 26], "computation": "angle_3points", "offset": -1.57, "scale": 1.0, "limits": [-2.53, 2.53]},
    "right_knee": {"source_landmarks": [24, 26, 28], "computation": "angle_3points", "scale": 1.0, "limits": [-0.26, 2.05]},
    "right_ankle_pitch": {"source_landmarks": [26, 28, 32], "computation": "angle_3points", "scale": 0.5, "limits": [-0.87, 0.52]},
    "right_ankle_roll": {"source_landmarks": [28, 30, 32], "computation": "angle_3points", "scale": 0.5, "limits": [-0.26, 0.26]},
    "waist_yaw": {"source_landmarks": [11, 12, 23, 24], "computation": "torso_twist", "scale": 0.5, "limits": [-2.35, 2.35]},
    "waist_roll": {"source_landmarks": [11, 12], "computation": "shoulder_tilt", "scale": 0.5, "limits": [-0.52, 0.52]},
    "left_shoulder_pitch": {"source_landmarks": [11, 13, 15], "computation": "angle_3points", "scale": 1.0, "limits": [-2.87, 2.87]},
    "left_shoulder_roll": {"source_landmarks": [12, 11, 13], "computation": "angle_3points", "scale": 1.0, "limits": [-1.34, 3.11]},
    "left_shoulder_yaw": {"source_landmarks": [11, 13, 15], "computation": "arm_twist", "scale": 0.5, "limits": [-2.79, 2.79]},
    "left_elbow": {"source_landmarks": [11, 13, 15], "computation": "angle_3points", "scale": 1.0, "limits": [-1.25, 2.61]},
    "right_shoulder_pitch": {"source_landmarks": [12, 14, 16], "computation": "angle_3points", "scale": 1.0, "limits": [-2.87, 2.87]},
    "right_shoulder_roll": {"source_landmarks": [11, 12, 14], "computation": "angle_3points", "scale": 1.0, "limits": [-3.11, 1.34]},
    "right_shoulder_yaw": {"source_landmarks": [12, 14, 16], "computation": "arm_twist", "scale": 0.5, "limits": [-2.79, 2.79]},
    "right_elbow": {"source_landmarks": [12, 14, 16], "computation": "angle_3points", "scale": 1.0, "limits": [-2.61, 1.25]}
  }
}
```

- [ ] **Step 2: Implement joint map loader**

```python
# packages/skill_foundry/skill_foundry_retarget/joint_map.py
"""Joint mapping configuration for human-to-robot retargeting."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

G1_JOINT_ORDER = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch",
    "left_knee", "left_ankle_pitch", "left_ankle_roll",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch",
    "right_knee", "right_ankle_pitch", "right_ankle_roll",
    "waist_yaw", "waist_roll",
    "left_shoulder_pitch", "left_shoulder_roll", "left_shoulder_yaw", "left_elbow",
    "left_wrist_roll", "left_wrist_pitch", "left_wrist_yaw",
    "right_shoulder_pitch", "right_shoulder_roll", "right_shoulder_yaw", "right_elbow",
    "right_wrist_roll", "right_wrist_pitch", "right_wrist_yaw",
    "head_yaw",
]


@dataclass
class JointMapping:
    """Mapping configuration for a single joint."""
    source_landmarks: List[int]
    computation: str
    scale: float = 1.0
    offset: float = 0.0
    limits: tuple = (-3.14, 3.14)
    reference_axis: Optional[List[float]] = None


@dataclass
class JointMap:
    """Complete joint mapping from source skeleton to target robot."""
    
    version: str
    source_skeleton: str
    target_robot: str
    mappings: Dict[str, JointMapping]
    
    @property
    def g1_joints(self) -> List[str]:
        return G1_JOINT_ORDER
    
    def get_mapping(self, joint_name: str) -> Optional[Dict[str, Any]]:
        if joint_name not in self.mappings:
            return None
        m = self.mappings[joint_name]
        return {
            "source_landmarks": m.source_landmarks, "computation": m.computation,
            "scale": m.scale, "offset": m.offset, "limits": m.limits,
            "reference_axis": m.reference_axis,
        }


def load_joint_map(path: Optional[Path] = None) -> JointMap:
    """Load joint mapping configuration from JSON file.
    
    Args:
        path: Path to joint_map.json. If None, uses default location.
        
    Returns:
        JointMap instance
    """
    if path is None:
        path = Path(__file__).parent.parent / "skill_foundry_validation" / "models" / "g1_description" / "joint_map.json"
    
    with open(path) as f:
        data = json.load(f)
    
    mappings = {}
    for name, cfg in data.get("mappings", {}).items():
        mappings[name] = JointMapping(
            source_landmarks=cfg["source_landmarks"], computation=cfg["computation"],
            scale=cfg.get("scale", 1.0), offset=cfg.get("offset", 0.0),
            limits=tuple(cfg.get("limits", [-3.14, 3.14])),
            reference_axis=cfg.get("reference_axis"),
        )
    
    return JointMap(
        version=data.get("version", "1.0"),
        source_skeleton=data.get("source_skeleton", "mediapipe_pose_33"),
        target_robot=data.get("target_robot", "unitree_g1_29dof"),
        mappings=mappings,
    )
```

- [ ] **Step 3: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_retarget/
git add packages/skill_foundry/skill_foundry_validation/models/g1_description/joint_map.json
git commit -m "feat(retarget): implement joint mapping configuration"
```

---

### Task 2.2: Retargeting Calculator

**Files:**
- Create: `packages/skill_foundry/skill_foundry_retarget/retarget.py`

- [ ] **Step 1: Implement retargeting calculator**

```python
# packages/skill_foundry/skill_foundry_retarget/retarget.py
"""Human-to-robot motion retargeting."""

from typing import Tuple
import numpy as np
from .joint_map import load_joint_map, JointMap, G1_JOINT_ORDER


def angle_3points(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    v1, v2 = p1 - p2, p3 - p2
    v1_norm, v2_norm = np.linalg.norm(v1), np.linalg.norm(v2)
    if v1_norm < 1e-6 or v2_norm < 1e-6:
        return 0.0
    cos_angle = np.clip(np.dot(v1, v2) / (v1_norm * v2_norm), -1.0, 1.0)
    return float(np.arccos(cos_angle))


class Retargeter:
    """Converts human pose landmarks to robot joint angles."""
    
    def __init__(self, joint_map: JointMap = None):
        self.joint_map = joint_map or load_joint_map()
        self.joint_names = G1_JOINT_ORDER
    
    def compute(self, landmarks: np.ndarray) -> np.ndarray:
        angles = np.zeros(29, dtype=np.float32)
        for i, joint_name in enumerate(self.joint_names):
            mapping = self.joint_map.get_mapping(joint_name)
            if mapping is None:
                continue
            angle = self._compute_joint_angle(landmarks, mapping)
            angle = angle * mapping["scale"] + mapping.get("offset", 0.0)
            angles[i] = np.clip(angle, mapping["limits"][0], mapping["limits"][1])
        return angles
    
    def _compute_joint_angle(self, landmarks: np.ndarray, mapping: dict) -> float:
        indices = mapping["source_landmarks"]
        computation = mapping["computation"]
        
        if computation == "angle_3points" and len(indices) >= 3:
            return angle_3points(landmarks[indices[0]], landmarks[indices[1]], landmarks[indices[2]])
        return 0.0
    
    def get_limits(self, joint_name: str) -> Tuple[float, float]:
        mapping = self.joint_map.get_mapping(joint_name)
        return tuple(mapping["limits"]) if mapping else (-3.14, 3.14)
```

- [ ] **Step 2: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_retarget/
git commit -m "feat(retarget): implement human-to-G1 retargeting calculator"
```

---

### Task 2.3: BVH to Reference Trajectory Converter

**Files:**
- Create: `packages/skill_foundry/skill_foundry_retarget/bvh_to_trajectory.py`
- Create: `packages/skill_foundry/skill_foundry_retarget/tests/test_bvh_to_trajectory.py`

- [ ] **Step 1: Write failing test**

```python
# packages/skill_foundry/skill_foundry_retarget/tests/test_bvh_to_trajectory.py
import pytest
from skill_foundry_retarget.bvh_to_trajectory import BVHToTrajectoryConverter

def test_converter_produces_reference_trajectory():
    """Converter should produce valid reference trajectory JSON."""
    converter = BVHToTrajectoryConverter()
    
    # Minimal BVH content
    bvh_content = """HIERARCHY
ROOT Hips
{
  OFFSET 0.0 0.0 0.0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  End Site
  {
    OFFSET 0.0 10.0 0.0
  }
}
MOTION
Frames: 2
Frame Time: 0.033333
0.0 0.0 0.0 0.0 0.0 0.0
1.0 0.0 0.0 0.0 0.0 0.0
"""
    
    trajectory = converter.convert(bvh_content)
    
    assert "joint_order" in trajectory
    assert "frames" in trajectory
    assert "dt" in trajectory
    assert len(trajectory["frames"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/skill_foundry
pytest skill_foundry_retarget/tests/test_bvh_to_trajectory.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement BVH to trajectory converter**

```python
# packages/skill_foundry/skill_foundry_retarget/bvh_to_trajectory.py
"""Convert BVH motion capture files to reference trajectory format."""

import re
from typing import Dict, List, Any
import numpy as np

from .joint_map import G1_JOINT_ORDER


class BVHToTrajectoryConverter:
    """Converts BVH files to AUROSY reference trajectory format."""
    
    def __init__(self):
        self.joint_order = G1_JOINT_ORDER
    
    def convert(self, bvh_content: str) -> Dict[str, Any]:
        """Convert BVH string to reference trajectory dict.
        
        Args:
            bvh_content: BVH file content as string
            
        Returns:
            Reference trajectory dict compatible with skill_foundry_preprocessing
        """
        frames_data, frame_time = self._parse_motion_section(bvh_content)
        
        trajectory_frames = []
        for frame_values in frames_data:
            joint_angles = self._bvh_frame_to_joint_angles(frame_values)
            trajectory_frames.append({
                "joint_angles_rad": joint_angles,
            })
        
        return {
            "version": "1.0",
            "robot": "unitree_g1_29dof",
            "joint_order": self.joint_order,
            "dt": frame_time,
            "frames": trajectory_frames,
            "source": "bvh_motion_capture",
        }
    
    def _parse_motion_section(self, bvh_content: str) -> tuple:
        """Parse MOTION section of BVH file."""
        motion_match = re.search(r"MOTION\s*\n", bvh_content)
        if not motion_match:
            return [], 0.033
        
        motion_section = bvh_content[motion_match.end():]
        lines = motion_section.strip().split("\n")
        
        frame_count = 0
        frame_time = 0.033
        frames = []
        
        for line in lines:
            line = line.strip()
            if line.startswith("Frames:"):
                frame_count = int(line.split(":")[1].strip())
            elif line.startswith("Frame Time:"):
                frame_time = float(line.split(":")[1].strip())
            elif line and not line.startswith(("Frames", "Frame Time")):
                values = [float(v) for v in line.split()]
                frames.append(values)
        
        return frames, frame_time
    
    def _bvh_frame_to_joint_angles(self, frame_values: List[float]) -> List[float]:
        """Convert BVH frame values to G1 joint angles.
        
        This is a simplified mapping - full implementation would need
        proper BVH skeleton parsing and FK computation.
        """
        angles = [0.0] * 29
        
        # BVH typically has: root pos (3) + root rot (3) + joint rots
        # For now, return zeros - full implementation requires BVH skeleton parsing
        
        return angles
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd packages/skill_foundry
pytest skill_foundry_retarget/tests/test_bvh_to_trajectory.py -v
```

Expected: PASS

- [ ] **Step 5: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_retarget/
git commit -m "feat(retarget): implement BVH to reference trajectory converter"
```

---

## Phase 3: Frontend - Camera UI & Live Track

**Objective:** Add webcam capture UI and real-time G1 preview to the frontend.

**Location:** `AUROSY_creators_factory/web/frontend/`

### Implementation status (current)

- Camera capture hook implemented: `web/frontend/src/hooks/useCameraCapture.ts`.
- Motion capture WebSocket hook implemented: `web/frontend/src/hooks/useMotionCaptureWs.ts`.
- Pose Studio integration completed through `web/frontend/src/components/MotionCapturePanel.tsx` and `web/frontend/src/pages/PoseStudio.tsx`.
- **Recording → platform artifact:** while WebSocket recording is active, MediaPipe landmark frames are buffered; on **Stop recording** the UI calls `POST /api/platform/artifacts/{name}` with JSON `{ "frames": [N,33,3] }` (same `X-User-Id` as the motion pipeline). The Motion pipeline panel field **Landmarks artifact** is auto-filled with that filename when upload succeeds.
- **Motion pipeline panel (`MotionPipelinePanel.tsx`):** default train path is **AMP** (`train_mode: amp`, config from `web/frontend/src/lib/motionPipelineTrainConfig.ts` with short vs standard `total_timesteps`). **Smoke** remains available as a quick contract-only job. **Build reference from landmarks** calls `build_reference` with `landmarks_artifact`.
- API client now includes:
  - `motionCaptureWebSocketUrl()` with `VITE_MOTION_CAPTURE_WS_URL` override
  - `runRetarget()` wrapper for `POST /api/pipeline/retarget`
  - `savePlatformArtifact()` for landmark dumps after capture
- Live Track state ownership is enforced in Pose Studio: while live tracking is active, manual pose editing/playback actions are gated to avoid joint-state conflicts.

### Task 3.1: Camera Capture Hook

**Files:**
- Create: `web/frontend/src/hooks/useCameraCapture.ts`

- [ ] **Step 1: Implement camera capture hook**

```typescript
// web/frontend/src/hooks/useCameraCapture.ts
import { useState, useCallback, useRef, useEffect } from 'react';

export function useCameraCapture() {
  const [isCapturing, setIsCapturing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const startCapture = useCallback(async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' }, audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      canvasRef.current = document.createElement('canvas');
      canvasRef.current.width = 640;
      canvasRef.current.height = 480;
      setIsCapturing(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to access camera');
    }
  }, []);

  const stopCapture = useCallback(() => {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setIsCapturing(false);
    setIsRecording(false);
  }, []);

  const captureFrame = useCallback((): Blob | null => {
    if (!videoRef.current || !canvasRef.current || !isCapturing) return null;
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(videoRef.current, 0, 0);
    const dataUrl = canvasRef.current.toDataURL('image/jpeg', 0.8);
    const binary = atob(dataUrl.split(',')[1]);
    const array = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) array[i] = binary.charCodeAt(i);
    return new Blob([array], { type: 'image/jpeg' });
  }, [isCapturing]);

  useEffect(() => () => streamRef.current?.getTracks().forEach(track => track.stop()), []);

  return { isCapturing, isRecording, error, videoRef, startCapture, stopCapture,
           startRecording: () => setIsRecording(true), stopRecording: () => setIsRecording(false), captureFrame };
}
```

- [ ] **Step 2: Commit implementation**

```bash
git add web/frontend/src/hooks/useCameraCapture.ts
git commit -m "feat(frontend): implement camera capture hook"
```

---

### Task 3.2: Motion Capture WebSocket Hook

**Files:**
- Create: `web/frontend/src/hooks/useMotionCaptureWs.ts`

- [ ] **Step 1: Implement WebSocket hook**

```typescript
// web/frontend/src/hooks/useMotionCaptureWs.ts
import { useState, useCallback, useRef, useEffect } from 'react';

export interface PoseData { landmarks: number[][]; confidence: number; timestamp_ms: number; }
export interface RecordingResult { bvh: string; duration_sec: number; frame_count: number; }

const DEFAULT_WS_URL = 'ws://localhost:8001/ws/capture';

export function useMotionCaptureWs() {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [latestPose, setLatestPose] = useState<PoseData | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const recordingPromiseRef = useRef<{ resolve: (r: RecordingResult | null) => void } | null>(null);

  const connect = useCallback((url = DEFAULT_WS_URL) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(url);
    ws.onopen = () => { setIsConnected(true); setError(null); };
    ws.onclose = () => { setIsConnected(false); setIsRecording(false); };
    ws.onerror = () => { setError('WebSocket error'); setIsConnected(false); };
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === 'pose') setLatestPose({ landmarks: data.landmarks, confidence: data.confidence, timestamp_ms: data.timestamp_ms });
      else if (data.type === 'recording_started') setIsRecording(true);
      else if (data.type === 'recording_stopped') {
        setIsRecording(false);
        recordingPromiseRef.current?.resolve({ bvh: data.bvh, duration_sec: data.duration_sec, frame_count: data.frame_count });
        recordingPromiseRef.current = null;
      }
    };
    wsRef.current = ws;
  }, []);

  const disconnect = useCallback(() => { wsRef.current?.close(); wsRef.current = null; setIsConnected(false); setIsRecording(false); setLatestPose(null); }, []);
  const sendFrame = useCallback((blob: Blob) => { if (wsRef.current?.readyState === WebSocket.OPEN) blob.arrayBuffer().then(b => wsRef.current?.send(b)); }, []);
  const startRecording = useCallback(() => { wsRef.current?.send(JSON.stringify({ type: 'start_recording' })); }, []);
  const stopRecording = useCallback(() => new Promise<RecordingResult | null>(resolve => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) { resolve(null); return; }
    recordingPromiseRef.current = { resolve };
    wsRef.current.send(JSON.stringify({ type: 'stop_recording' }));
    setTimeout(() => { recordingPromiseRef.current?.resolve(null); recordingPromiseRef.current = null; }, 5000);
  }), []);

  useEffect(() => () => { wsRef.current?.close(); }, []);

  return { isConnected, isRecording, latestPose, error, connect, disconnect, sendFrame, startRecording, stopRecording };
}
```

- [ ] **Step 2: Commit implementation**

```bash
git add web/frontend/src/hooks/useMotionCaptureWs.ts
git commit -m "feat(frontend): implement motion capture WebSocket hook"
```

---

### Task 3.3: Motion Capture Panel Component

**Files:**
- Create: `web/frontend/src/components/MotionCapturePanel.tsx`

- [ ] **Step 1: Implement motion capture panel**

```tsx
// web/frontend/src/components/MotionCapturePanel.tsx
import { useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useCameraCapture } from '../hooks/useCameraCapture';
import { useMotionCaptureWs, RecordingResult } from '../hooks/useMotionCaptureWs';

interface Props {
  onPoseUpdate?: (landmarks: number[][]) => void;
  onRecordingComplete?: (result: RecordingResult) => void;
  motionCaptureUrl?: string;
}

export function MotionCapturePanel({ onPoseUpdate, onRecordingComplete, motionCaptureUrl }: Props) {
  const { t } = useTranslation();
  const camera = useCameraCapture();
  const ws = useMotionCaptureWs();
  const frameIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (camera.isCapturing && ws.isConnected) {
      frameIntervalRef.current = window.setInterval(() => {
        const frame = camera.captureFrame();
        if (frame) ws.sendFrame(frame);
      }, 33);
    }
    return () => { if (frameIntervalRef.current) clearInterval(frameIntervalRef.current); };
  }, [camera.isCapturing, ws.isConnected]);

  useEffect(() => { if (ws.latestPose && onPoseUpdate) onPoseUpdate(ws.latestPose.landmarks); }, [ws.latestPose, onPoseUpdate]);

  const handleStartCapture = useCallback(async () => { await camera.startCapture(); ws.connect(motionCaptureUrl); }, []);
  const handleStopCapture = useCallback(() => { camera.stopCapture(); ws.disconnect(); }, []);
  const handleStopRecording = useCallback(async () => { const r = await ws.stopRecording(); if (r && onRecordingComplete) onRecordingComplete(r); }, []);

  return (
    <div className="motion-capture-panel">
      <video ref={camera.videoRef} autoPlay playsInline muted style={{ width: '100%', maxWidth: 640, background: '#000' }} />
      {ws.latestPose && <div>{t('motionCapture.confidence')}: {(ws.latestPose.confidence * 100).toFixed(0)}%</div>}
      <div className="controls">
        {!camera.isCapturing ? (
          <button onClick={handleStartCapture}>{t('motionCapture.startCamera')}</button>
        ) : (
          <>
            <button onClick={handleStopCapture}>{t('motionCapture.stopCamera')}</button>
            {!ws.isRecording ? (
              <button onClick={ws.startRecording} disabled={!ws.isConnected}>{t('motionCapture.startRecording')}</button>
            ) : (
              <button onClick={handleStopRecording}>{t('motionCapture.stopRecording')}</button>
            )}
          </>
        )}
      </div>
      {(camera.error || ws.error) && <div className="error">{camera.error || ws.error}</div>}
      <div className="status">
        <span className={ws.isConnected ? 'connected' : 'disconnected'}>{ws.isConnected ? t('motionCapture.connected') : t('motionCapture.disconnected')}</span>
        {ws.isRecording && <span className="recording">{t('motionCapture.recording')}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add i18n translations to en.json**

```json
"motionCapture": {
  "title": "Motion Capture",
  "startCamera": "Start Camera",
  "stopCamera": "Stop Camera",
  "startRecording": "Start Recording",
  "stopRecording": "Stop Recording",
  "confidence": "Confidence",
  "connected": "Connected",
  "disconnected": "Disconnected",
  "recording": "Recording..."
}
```

- [ ] **Step 3: Commit implementation**

```bash
git add web/frontend/src/components/MotionCapturePanel.tsx
git add web/frontend/src/locales/en.json
git commit -m "feat(frontend): implement motion capture panel component"
```

---

## Phase 4: AMP RL Training Pipeline

**Objective:** Add an AMP training path to the existing RL worker so motion imitation can run through `skill-foundry-train --mode amp` while keeping `smoke` / PPO modes backward-compatible.

**Location:** `packages/skill_foundry/skill_foundry_rl/`

### Implementation status (current)

- AMP mode is available in CLI dispatch: `packages/skill_foundry/skill_foundry_rl/cli.py` (`--mode amp`).
- Core AMP modules are implemented:
  - `packages/skill_foundry/skill_foundry_rl/reference_motion.py`
  - `packages/skill_foundry/skill_foundry_rl/amp_discriminator.py`
  - `packages/skill_foundry/skill_foundry_rl/amp_train.py`
- Platform API/queue mode contracts now accept AMP:
  - `web/backend/app/main.py` (`TrainRequest`, `CreateTrainJobRequest`)
  - `web/backend/app/platform_enqueue.py` (enqueue mode type)
- Tests added:
  - `packages/skill_foundry/skill_foundry_rl/tests/test_reference_motion.py`
  - `packages/skill_foundry/skill_foundry_rl/tests/test_amp_discriminator.py`
  - `packages/skill_foundry/skill_foundry_rl/tests/test_amp_train_short.py`
  - `packages/skill_foundry/skill_foundry_rl/tests/test_cli_amp_mode.py`

### Task 4.0: Validate AMP pipeline wiring

- [ ] **Step 1: Run AMP unit tests**

```bash
pytest /Users/sarkhan/AUROSY_creators_factory_platform/packages/skill_foundry/skill_foundry_rl/tests/test_reference_motion.py \
  /Users/sarkhan/AUROSY_creators_factory_platform/packages/skill_foundry/skill_foundry_rl/tests/test_amp_discriminator.py \
  /Users/sarkhan/AUROSY_creators_factory_platform/packages/skill_foundry/skill_foundry_rl/tests/test_cli_amp_mode.py -q
```

- [ ] **Step 2: Run short AMP training smoke**

```bash
pytest /Users/sarkhan/AUROSY_creators_factory_platform/packages/skill_foundry/skill_foundry_rl/tests/test_amp_train_short.py -q
```

- [ ] **Step 3: Verify backend API keeps AMP mode in contracts**

```bash
python -m pytest /Users/sarkhan/AUROSY_creators_factory_platform/web/backend/tests/test_retarget_api.py -q
```

### Task 4.1: Reference Motion Loader

**Files:**
- Create: `packages/skill_foundry/skill_foundry_rl/reference_motion.py`

- [ ] **Step 1: Implement reference motion loader**

```python
# packages/skill_foundry/skill_foundry_rl/reference_motion.py
"""Reference motion loading and sampling for AMP training."""

import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np


class ReferenceMotion:
    def __init__(self, frames: np.ndarray, dt: float, joint_order: List[str]):
        self.frames = frames
        self.dt = dt
        self.joint_order = joint_order
    
    @property
    def num_frames(self) -> int: return self.frames.shape[0]
    @property
    def num_joints(self) -> int: return self.frames.shape[1]
    @property
    def duration(self) -> float: return (self.num_frames - 1) * self.dt
    
    def sample(self, t: float) -> np.ndarray:
        if self.num_frames == 1: return self.frames[0].copy()
        t = np.clip(t, 0.0, self.duration)
        frame_idx = t / self.dt
        idx0 = int(np.floor(frame_idx))
        idx1 = min(idx0 + 1, self.num_frames - 1)
        alpha = frame_idx - idx0
        return (1 - alpha) * self.frames[idx0] + alpha * self.frames[idx1]
    
    def sample_batch(self, times: np.ndarray) -> np.ndarray:
        return np.array([self.sample(t) for t in times])
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReferenceMotion":
        frames = np.array([f.get("joint_angles_rad", f.get("q", [])) for f in data.get("frames", [])], dtype=np.float32)
        return cls(frames=frames, dt=data.get("dt", 0.02), joint_order=data.get("joint_order", []))
    
    @classmethod
    def from_json(cls, path: Path) -> "ReferenceMotion":
        with open(path) as f: return cls.from_dict(json.load(f))


def load_reference_motion(path: Path) -> ReferenceMotion:
    return ReferenceMotion.from_json(path)
```

- [ ] **Step 2: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_rl/reference_motion.py
git commit -m "feat(rl): implement reference motion loader for AMP"
```

---

### Task 4.2: AMP Discriminator

**Files:**
- Create: `packages/skill_foundry/skill_foundry_rl/amp_discriminator.py`

- [ ] **Step 1: Implement AMP discriminator**

```python
# packages/skill_foundry/skill_foundry_rl/amp_discriminator.py
"""Adversarial Motion Prior discriminator for motion imitation."""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple


class AMPDiscriminator(nn.Module):
    def __init__(self, state_dim: int, hidden_dim: int = 256, num_layers: int = 2):
        super().__init__()
        input_dim = state_dim * 2
        layers = [nn.Linear(input_dim, hidden_dim), nn.ReLU()]
        for _ in range(num_layers - 1):
            layers.extend([nn.Linear(hidden_dim, hidden_dim), nn.ReLU()])
        layers.append(nn.Linear(hidden_dim, 1))
        self.net = nn.Sequential(*layers)
        self.grad_penalty_coef = 10.0
    
    def forward(self, states: torch.Tensor, next_states: torch.Tensor) -> torch.Tensor:
        return self.net(torch.cat([states, next_states], dim=-1))
    
    def compute_reward(self, states: torch.Tensor, next_states: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            scores = self.forward(states, next_states)
            return (-torch.log(1 - torch.sigmoid(scores) + 1e-8)).squeeze(-1)
    
    def compute_loss(self, expert_states, expert_next, policy_states, policy_next) -> Tuple[torch.Tensor, dict]:
        expert_scores = self.forward(expert_states, expert_next)
        policy_scores = self.forward(policy_states, policy_next)
        expert_loss = F.binary_cross_entropy_with_logits(expert_scores, torch.ones_like(expert_scores))
        policy_loss = F.binary_cross_entropy_with_logits(policy_scores, torch.zeros_like(policy_scores))
        total_loss = expert_loss + policy_loss
        return total_loss, {"disc_expert_loss": expert_loss.item(), "disc_policy_loss": policy_loss.item(),
                           "disc_expert_score": expert_scores.mean().item(), "disc_policy_score": policy_scores.mean().item()}
```

- [ ] **Step 2: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_rl/amp_discriminator.py
git commit -m "feat(rl): implement AMP discriminator for motion imitation"
```

---

## Phase 5: Eval & Export Extensions

**Objective:** Extend evaluation and export tooling so AMP-trained checkpoints can be validated against reference motion quality and exported with motion-specific metadata required for deployment.

**Location:** `packages/skill_foundry/skill_foundry_rl/`, `packages/skill_foundry/`, `web/backend/`

### Implementation status (current)

- AMP training artifacts are produced through `skill_foundry_rl/amp_train.py`.
- **Motion eval:** `skill_foundry_rl/motion_eval.py` builds `eval_motion.json` (`schema_version` `1.0`): tracking MSE (per joint + mean), velocity MSE vs reference, optional discriminator summary from `amp_discriminator.pt`; `foot_sliding` is an **ankle velocity energy proxy** on rollout `motor_q` (not MuJoCo contact-based).
- **CLI:** `skill-foundry-train --mode amp --eval-only --checkpoint … [--discriminator …] [--eval-output …]` (still uses `--reference-trajectory` and `--config` with top-level `mode: amp`).
- **Export:** optional `manifest.motion`, `eval_motion.json` in tarball, `--include-amp-discriminator` / `include_amp_discriminator` on pack; JSON Schema updated under `contracts/export/export_manifest.schema.json`.
- **Platform API:** `CreateTrainJobRequest` supports `eval_only`, `checkpoint_artifact`, `motion_export`; workspace includes `platform_motion.json` and `policy_checkpoint.zip` when applicable; worker invokes eval-only CLI. `TrainRequest` supports synchronous `eval_only` + `checkpoint_path`. Packaging reads `motion_export` from `platform_motion.json` for `skill-foundry-package` flags.

### Task 5.1: Motion Evaluation Metrics and Report Contract

**Files:**
- Update: `packages/skill_foundry/skill_foundry_rl/cli.py`
- Create: `packages/skill_foundry/skill_foundry_rl/motion_eval.py`
- Create: `packages/skill_foundry/skill_foundry_rl/tests/test_motion_eval.py`

- [x] **Step 1: Define metrics contract**
  - Include: tracking MSE per joint, velocity consistency, foot-sliding proxy, discriminator realism score.
  - Foot-sliding: `metrics.foot_sliding` is a dict `ankle_velocity_energy` on rollout motor indices (4,5,10,11), not MuJoCo contact traces.
  - Persist machine-readable report as `eval_motion.json`.

- [x] **Step 2: Implement `motion_eval.py`**
  - Add pure functions for metric computation from rollout traces and reference motion.
  - Add report serializer with schema version (e.g. `"schema_version": "1.0"`).

- [x] **Step 3: Add CLI entrypoint for AMP evaluation**
  - Extend CLI with `skill-foundry-train --mode amp --eval-only` path.
  - Ensure compatibility with existing smoke/PPO flags.

- [x] **Step 4: Add tests**
  - Unit tests for each metric function.
  - Contract test ensuring generated `eval_motion.json` contains required keys.

- [ ] **Step 5: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_rl/motion_eval.py
git add packages/skill_foundry/skill_foundry_rl/cli.py
git add packages/skill_foundry/skill_foundry_rl/tests/test_motion_eval.py
git commit -m "feat(rl): add AMP motion evaluation metrics and report contract"
```

---

### Task 5.2: Export Manifest Extensions for Motion Skills

**Files:**
- Update: `packages/skill_foundry/skill_foundry_export/` (or equivalent export module)
- Update: `packages/skill_foundry/README.md`
- Update: `docs/archive/10_phase4_manifest_export.md`

- [x] **Step 1: Extend manifest schema**
  - Add motion section with:
    - `reference_motion_source` (bvh/json URI)
    - `retarget_profile` (robot + map version)
    - `eval_report` (path to `eval_motion.json`)
    - `amp` (discriminator/policy metadata)

- [x] **Step 2: Wire export CLI**
  - Ensure exported bundle includes:
    - policy checkpoint
    - discriminator checkpoint (if used at runtime)
    - motion eval report
    - manifest with new motion section

- [x] **Step 3: Add backward compatibility rules**
  - Existing non-motion bundles should remain valid without new motion fields.
  - New fields should be optional with sane defaults.

- [x] **Step 4: Document schema changes**
  - Update docs with manifest examples and migration notes.

- [ ] **Step 5: Commit implementation**

```bash
git add packages/skill_foundry/
git add docs/archive/10_phase4_manifest_export.md
git commit -m "feat(export): extend skill bundle manifest for motion artifacts"
```

---

### Task 5.3: Backend API Support for Eval and Export Metadata

**Files:**
- Update: `web/backend/app/main.py`
- Update: `web/backend/app/platform_enqueue.py`
- Create/Update: `web/backend/tests/test_motion_eval_export_api.py`

- [x] **Step 1: Extend API request/response models**
  - Add fields for `eval_report_path`, `retarget_profile`, and motion export options.

- [x] **Step 2: Extend enqueue contracts**
  - Propagate motion eval/export parameters into worker payload.
  - Keep legacy payload shape accepted by workers.

- [x] **Step 3: Add tests**
  - Validate request model parsing.
  - Validate queue payload includes motion fields when requested.

- [ ] **Step 4: Commit implementation**

```bash
git add web/backend/app/main.py
git add web/backend/app/platform_enqueue.py
git add web/backend/tests/test_motion_eval_export_api.py
git commit -m "feat(api): add motion eval/export fields to backend contracts"
```

---

## Phase 6: Motion Skill Bundle & End-to-End Flow

**Objective:** Deliver a full user journey from webcam capture to deployable skill bundle, including orchestration, validations, and operator-facing runbook.

**Location:** `web/backend/`, `packages/skill_foundry/`, `web/frontend/`, `docs/skill_foundry/`

### Implementation status (current)

- **Orchestration:** `web/backend/app/services/motion_pipeline.py` persists per-user state under `users/<user_id>/motion_pipelines/<pipeline_id>/state.json` (stages: `capture`, `reference`, `train`, `eval`, `export` with `status`, `completed_at`, `error`, plus `job_id` / `package_id` where applicable).
- **API:** `POST /api/pipeline/motion/run` (body: `pipeline_id`, `action`, optional artifacts and train fields) and `GET /api/pipeline/motion/{pipeline_id}` — see `web/backend/app/main.py`. Idempotency: repeating `enqueue_train` or `request_pack` with the same `pipeline_id` returns the existing `job_id` / `package_id` unless `force: true`.
- **Reference build:** `action: build_reference` accepts either `reference_artifact` (copy from `POST /api/platform/artifacts/{name}`) or `landmarks_artifact` (JSON array `[N,33,3]` or `{ "landmarks": ... }` / `{ "frames": ... }`) plus server-side retargeting into `reference_trajectory.json` in the pipeline directory.
- **`GET /api/meta`:** exposes `motion_pipeline_enabled` and optional `motion_publish_max_mse` (`G1_MOTION_PUBLISH_MAX_MSE`).

### Task 6.1: Pipeline Orchestration Contract

**Files:**
- Update: `web/backend/app/main.py`
- Create/Update: `web/backend/app/services/motion_pipeline.py`
- Create/Update: `web/backend/tests/test_motion_pipeline_flow.py`

- [x] **Step 1: Define explicit stage machine**
  - Stages in state: `capture` → `reference` → `train` → `eval` → `export` (aligned with capture → retarget/reference → train → eval → pack).
  - Persist stage timestamps and failure reasons.

- [x] **Step 2: Add idempotent orchestration endpoint**
  - `POST /api/pipeline/motion/run` with stable `pipeline_id` (not train `job_id` — the train job id is stored inside state when enqueued).
  - Re-running `enqueue_train` / `request_pack` without `force` is safe for duplicate side effects.

- [x] **Step 3: Add integration test**
  - `web/backend/tests/test_motion_pipeline_flow.py` covers init, `build_reference`, enqueue idempotency.

- [ ] **Step 4: Commit implementation**

```bash
git add web/backend/app/services/motion_pipeline.py
git add web/backend/app/main.py
git add web/backend/tests/test_motion_pipeline_flow.py
git commit -m "feat(pipeline): add end-to-end motion pipeline orchestration"
```

---

### Task 6.2: Bundle Composition and Validation Gate

**Files:**
- Update: `packages/skill_foundry/` bundle builder modules (existing `package_skill` / manifest motion section — unchanged)
- Create: `packages/skill_foundry/skill_foundry_export/motion_bundle_validate.py`
- Create: `packages/skill_foundry/tests/test_motion_bundle_validation.py`

- [x] **Step 1: Implement motion bundle assembly**
  - Assembly remains `skill-foundry-package` + `POST /api/packages/from-job` / pipeline `request_pack` (reuses existing pack path).

- [x] **Step 2: Add validation gate before publish**
  - When `manifest.motion` is present, `PATCH /api/packages/{id}` with `published: true` runs `validate_motion_skill_bundle` (requires `eval_motion.json`, optional cap `G1_MOTION_PUBLISH_MAX_MSE` vs `metrics.tracking_mean_mse`).
  - Product validation gate (`validation_passed`) remains unchanged and runs first.

- [x] **Step 3: Add bundle validation tests**
  - `packages/skill_foundry/tests/test_motion_bundle_validation.py`

- [ ] **Step 4: Commit implementation**

```bash
git add packages/skill_foundry/
git commit -m "feat(bundle): add motion bundle assembly and validation gate"
```

---

### Task 6.3: End-to-End Operator UX and Runbook

**Files:**
- Update: `AUROSY_creators_factory/web/frontend/src/pages/PoseStudio.tsx` (embeds `MotionPipelinePanel`)
- Add: `AUROSY_creators_factory/web/frontend/src/components/MotionPipelinePanel.tsx`
- Update: `AUROSY_creators_factory/web/frontend/src/api/client.ts`, `src/lib/platformIdentity.ts`, locales, `styles.css`
- Update: `docs/skill_foundry/03_implementation_plan.md`
- Update: `docs/skill_foundry/README.md`

- [x] **Step 1: Add frontend pipeline progress timeline**
  - Timeline for stages `capture` … `export`; errors shown per stage after `GET`/`POST` sync. Actions: New run, Refresh, Load reference, Enqueue train, Sync job status, Create bundle, Download bundle.

- [x] **Step 2: Add artifact summary panel**
  - Job id and package id displayed when present; download uses existing `GET /api/packages/{id}/download`.

- [x] **Step 3: Write runbook for operators** (minimal — expand in ops docs as needed)
  - **Preconditions:** backend with Phase 5 (`G1_PLATFORM_DATA_DIR`, worker enabled for train), `GET /api/meta` returns `mjcf_default` for AMP env in the panel; optional motion-capture WS for live camera (`VITE_MOTION_CAPTURE_WS_URL` in UI repo).
  - **Standard flow (reference file):** `POST /api/platform/artifacts/{name}` with `reference_trajectory.json` → Motion Studio: New run → paste artifact name → **Load reference** → **Enqueue train** (default AMP; pick Short or Standard size, or switch to Smoke) → Sync / wait for job success → **Create bundle** → Download.
  - **Standard flow (webcam landmarks):** Start camera + motion-capture service → Start/Stop recording → UI saves `capture-landmarks-*.json` as artifact → **Build reference from landmarks** → Enqueue train → …
  - **Recovery:** same `pipeline_id` (stored in `sessionStorage` key `g1_motion_pipeline_id` in the SPA) + `Sync` refreshes job-linked stages; use `force: true` on `enqueue_train` or `request_pack` via API to replace failed attempts.

- [ ] **Step 4: Commit implementation**

```bash
git add web/frontend/src/pages/PoseStudio.tsx
git add web/frontend/src/components/MotionCapturePanel.tsx
git add docs/skill_foundry/03_implementation_plan.md
git add docs/skill_foundry/README.md
git commit -m "docs(frontend): add end-to-end motion pipeline UX and runbook"
```

---

## Verification Checkpoints

### Phase 1 Verification

```bash
cd packages/motion_capture
pip install -e ".[dev]"
motion-capture-server &
curl http://localhost:8001/health
pytest tests/ -v
```

### Phase 2 Verification

```bash
cd packages/skill_foundry
pip install -e "."
pytest skill_foundry_retarget/tests/ -v

# Optional API smoke:
cd ../../web/backend
python -m pytest tests/test_retarget_api.py -v
```

### Phase 3 Verification

```bash
cd web/frontend
npm install
npm run build
npm run test
# Optional: npm run typecheck (current repo may contain unrelated pre-existing TS warnings)
# Open browser to /pose, enable Camera Live Track panel
# Verify flow: Camera -> WS /ws/capture -> POST /api/pipeline/retarget -> MuJoCo G1 preview updates
```

### Phase 5 Verification

```bash
cd packages/skill_foundry
pytest skill_foundry_rl/tests/test_motion_eval.py -q

# AMP eval-only path writes eval_motion.json
skill-foundry-train --mode amp --eval-only --checkpoint /tmp/amp_ckpt.pt --reference-trajectory /tmp/reference_trajectory.json --config /tmp/train_config.json
```

### Phase 6 Verification

```bash
# Backend orchestration integration tests
python -m pytest web/backend/tests/test_motion_pipeline_flow.py -q

# Bundle validation gate tests
cd packages/skill_foundry
pytest tests/test_motion_bundle_validation.py -q

# Manual E2E smoke:
# 1) Capture motion in Pose Studio
# 2) Run retarget + AMP train + eval + export pipeline
# 3) Confirm exported bundle contains manifest, eval report, checkpoints, reference motion
```

---

## Critical Architecture Decisions

### Decision 1: Asynchronous Training

**Choice:** Job queue with polling from UI

**Rationale:** AMP training takes hours. Synchronous HTTP requests would timeout. The existing Phase 5 job queue infrastructure provides the foundation.

### Decision 2: BVH Storage

**Choice:** Local storage in user workspace with upload to Vast.ai

**Rationale:** BVH files can be large (10-50MB). Local storage simplifies the MVP. The existing vast_training/ sync mechanism handles upload.

### Decision 3: MediaPipe vs ViTPose

**Choice:** MediaPipe as default, ViTPose as optional

**Rationale:** MediaPipe runs on CPU without GPU. ViTPose provides higher quality but requires GPU.

**Implementation note:** `packages/motion_capture` reads **`MOTION_CAPTURE_BACKEND`** (`mediapipe` default). Selecting `vitpose` requires optional deps (`pip install -e ".[vitpose]"`) and a GPU-capable runtime; until a full ViTPose→33-landmark path is wired, the server may raise a clear configuration error (see package README).

---

## Related Documents

- [02_architecture.md](02_architecture.md) — Overall Skill Foundry architecture
- [04_cortex_pipeline.md](04_cortex_pipeline.md) — Cortex NMR + RL pipeline
- [08_phase3_rl_worker_docker.md](../archive/08_phase3_rl_worker_docker.md) — RL Docker setup
- [09_phase3_env_rewards.md](../archive/09_phase3_env_rewards.md) — Environment and rewards
- [10_phase4_manifest_export.md](../archive/10_phase4_manifest_export.md) — Skill bundle export
- [../deployment/vast-ai-training.md](../deployment/vast-ai-training.md) — Cloud GPU training

---

## Critical Architecture Decisions

### Decision 1: Asynchronous Training

**Choice:** Job queue with polling from UI

**Rationale:** AMP training takes hours. Synchronous HTTP requests would timeout. The existing Phase 5 job queue infrastructure (`G1_PLATFORM_WORKER_ENABLED`) provides the foundation.

**Implementation:** Extend existing job types to include `motion_training`. Frontend polls `/api/jobs/{id}` for status.

### Decision 2: BVH Storage

**Choice:** Local storage in user workspace with upload to Vast.ai

**Rationale:** BVH files can be large (10-50MB for long recordings). Local storage simplifies the MVP. The existing `vast_training/` sync mechanism handles upload to cloud workers.

**Implementation:** Store in `data/platform/users/{user_id}/motions/`. Upload via `setup_vast.sh` or rsync before training.

### Decision 3: MediaPipe vs ViTPose

**Choice:** MediaPipe as default, ViTPose as optional

**Rationale:** MediaPipe runs on CPU without GPU, making it accessible to all users. ViTPose provides higher quality but requires GPU.

**Implementation:** `motion_capture.pose_backend` abstraction allows swapping backends. Default to MediaPipe, enable ViTPose via config.
