# Video-to-Motion Integration: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable users to record human motion via webcam, preview it on G1 robot model in real-time, and train RL policies that imitate the captured motion using AMP (Adversarial Motion Priors).

**Architecture:** Six-layer integration extending existing Skill Foundry pipeline. Motion Capture Service (new microservice) → Retargeting Engine (new module in skill_foundry) → MuJoCo Browser Live Track (frontend extension) → AMP RL Training (new train_motion.py) → Extended Eval/Export → Motion Skill Bundle.

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
    # This test requires a fixture image with a person
    # For now, verify the interface works with empty frame
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = backend.process_frame(frame)
    # Empty frame should return None landmarks (no detection)
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
    landmarks: Optional[np.ndarray]  # Shape: (33, 3) for MediaPipe, xyz normalized
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
        """Process frame and extract 33 pose landmarks.
        
        Args:
            frame: RGB image array, shape (H, W, 3)
            
        Returns:
            PoseResult with landmarks array (33, 3) or None if no detection
        """
        timestamp_ms = time.time() * 1000
        
        results = self._pose.process(frame)
        
        if results.pose_landmarks is None:
            return PoseResult(
                landmarks=None,
                timestamp_ms=timestamp_ms,
                confidence=0.0,
            )
        
        landmarks = np.array([
            [lm.x, lm.y, lm.z]
            for lm in results.pose_landmarks.landmark
        ], dtype=np.float32)
        
        avg_visibility = np.mean([
            lm.visibility for lm in results.pose_landmarks.landmark
        ])
        
        return PoseResult(
            landmarks=landmarks,
            timestamp_ms=timestamp_ms,
            confidence=float(avg_visibility),
        )
    
    def close(self) -> None:
        """Release MediaPipe resources."""
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

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/motion_capture
pytest tests/test_bvh_export.py -v
```

Expected: FAIL with "No module named 'motion_capture.bvh_export'"

- [ ] **Step 3: Implement BVH exporter**

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


# MediaPipe landmark indices for skeleton hierarchy
MEDIAPIPE_SKELETON = {
    "Hips": 23,  # left_hip as root approximation
    "Spine": 11,  # left_shoulder approximation
    "Neck": 0,   # nose
    "Head": 0,
    "LeftShoulder": 11,
    "LeftArm": 13,
    "LeftForeArm": 15,
    "LeftHand": 17,
    "RightShoulder": 12,
    "RightArm": 14,
    "RightForeArm": 16,
    "RightHand": 18,
    "LeftUpLeg": 23,
    "LeftLeg": 25,
    "LeftFoot": 27,
    "RightUpLeg": 24,
    "RightLeg": 26,
    "RightFoot": 28,
}


class BVHExporter:
    """Export RecordingSession to BVH format."""
    
    def __init__(self, scale: float = 100.0):
        """Initialize exporter.
        
        Args:
            scale: Scale factor for positions (MediaPipe uses normalized coords)
        """
        self.scale = scale
    
    def export(self, session: RecordingSession) -> str:
        """Export session to BVH string.
        
        Args:
            session: RecordingSession with accumulated frames
            
        Returns:
            BVH file content as string
        """
        lines = []
        
        # HIERARCHY section
        lines.append("HIERARCHY")
        lines.append("ROOT Hips")
        lines.append("{")
        lines.append("  OFFSET 0.0 0.0 0.0")
        lines.append("  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation")
        
        # Simplified skeleton - just key joints
        self._add_joint(lines, "Spine", 2)
        self._add_joint(lines, "LeftUpLeg", 2)
        self._add_joint(lines, "RightUpLeg", 2)
        
        lines.append("}")
        
        # MOTION section
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
        """Add a joint to hierarchy."""
        prefix = "  " * indent
        lines.append(f"{prefix}JOINT {name}")
        lines.append(f"{prefix}{{")
        lines.append(f"{prefix}  OFFSET 0.0 10.0 0.0")
        lines.append(f"{prefix}  CHANNELS 3 Zrotation Xrotation Yrotation")
        lines.append(f"{prefix}  End Site")
        lines.append(f"{prefix}  {{")
        lines.append(f"{prefix}    OFFSET 0.0 10.0 0.0")
        lines.append(f"{prefix}  }}")
        lines.append(f"{prefix}}}")
    
    def _landmarks_to_frame_data(self, landmarks: np.ndarray) -> List[float]:
        """Convert landmarks to BVH frame data (positions + rotations)."""
        # Root position from hips
        hip_idx = MEDIAPIPE_SKELETON["Hips"]
        root_pos = landmarks[hip_idx] * self.scale
        
        # Simplified: return root position + zero rotations for all joints
        # Full implementation would compute actual joint angles
        frame_data = [
            root_pos[0], root_pos[1], root_pos[2],  # Root position
            0.0, 0.0, 0.0,  # Root rotation
            0.0, 0.0, 0.0,  # Spine rotation
            0.0, 0.0, 0.0,  # LeftUpLeg rotation
            0.0, 0.0, 0.0,  # RightUpLeg rotation
        ]
        return frame_data
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd packages/motion_capture
pytest tests/test_bvh_export.py -v
```

Expected: PASS

- [ ] **Step 5: Commit implementation**

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

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/motion_capture
pytest tests/test_server.py -v
```

Expected: FAIL with "No module named 'motion_capture.server'"

- [ ] **Step 3: Implement WebSocket server**

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
    """Create FastAPI application."""
    app = FastAPI(title="AUROSY Motion Capture Service")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
                        await websocket.send_json({
                            "type": "recording_started"
                        })
                    
                    elif msg_type == "stop_recording":
                        bvh_content = session.stop_recording()
                        await websocket.send_json({
                            "type": "recording_stopped",
                            "bvh": bvh_content,
                            "duration_sec": session.recording.duration_sec,
                            "frame_count": session.recording.frame_count,
                        })
                
                elif "bytes" in message:
                    frame_data = message["bytes"]
                    result = session.process_frame(frame_data)
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

- [ ] **Step 4: Run test to verify it passes**

```bash
cd packages/motion_capture
pip install -e ".[dev]"
pytest tests/test_server.py -v
```

Expected: PASS

- [ ] **Step 5: Commit implementation**

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

# Install OpenCV dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy package
COPY packages/motion_capture /app/packages/motion_capture

# Install package
RUN pip install --no-cache-dir /app/packages/motion_capture

EXPOSE 8001

ENTRYPOINT ["motion-capture-server"]
```

- [ ] **Step 2: Create README**

```markdown
# Motion Capture Service Docker

## Build

```bash
cd /path/to/AUROSY_creators_factory_platform
docker build -f docker/motion_capture/Dockerfile -t aurosy/motion-capture:latest .
```

## Run

```bash
docker run -p 8001:8001 aurosy/motion-capture:latest
```

## Test

```bash
curl http://localhost:8001/health
```
```

- [ ] **Step 3: Commit Docker setup**

```bash
git add docker/motion_capture/
git commit -m "feat(motion-capture): add Docker container"
```

---

## Phase 2: Retargeting Engine

**Objective:** Create a module that maps human skeleton (MediaPipe 33 landmarks) to G1 robot joint angles, respecting kinematic constraints.

**Location:** `packages/skill_foundry/skill_foundry_retarget/` (new subpackage)

### Task 2.1: Joint Mapping Configuration

**Files:**
- Create: `packages/skill_foundry/skill_foundry_retarget/__init__.py`
- Create: `packages/skill_foundry/skill_foundry_retarget/joint_map.py`
- Create: `packages/skill_foundry/skill_foundry_validation/models/g1_description/joint_map.json`

- [ ] **Step 1: Write failing test for joint mapping**

```python
# packages/skill_foundry/skill_foundry_retarget/tests/test_joint_map.py
import pytest
from skill_foundry_retarget.joint_map import JointMap, load_joint_map

def test_load_joint_map_returns_valid_mapping():
    """Joint map should load and contain G1 joints."""
    joint_map = load_joint_map()
    
    assert isinstance(joint_map, JointMap)
    assert "left_hip_pitch" in joint_map.g1_joints
    assert "right_knee" in joint_map.g1_joints
    assert len(joint_map.g1_joints) == 29  # G1 has 29 DOF

def test_joint_map_has_mediapipe_mapping():
    """Each G1 joint should map to MediaPipe landmarks."""
    joint_map = load_joint_map()
    
    mapping = joint_map.get_mapping("left_hip_pitch")
    assert mapping is not None
    assert "source_landmarks" in mapping
    assert "scale" in mapping
    assert "limits" in mapping
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/skill_foundry
pytest skill_foundry_retarget/tests/test_joint_map.py -v
```

Expected: FAIL with module not found

- [ ] **Step 3: Create joint_map.json configuration**

```json
{
  "version": "1.0",
  "source_skeleton": "mediapipe_pose_33",
  "target_robot": "unitree_g1_29dof",
  "mappings": {
    "left_hip_yaw": {
      "source_landmarks": [23, 25],
      "computation": "angle_between_vectors",
      "reference_axis": [0, 0, 1],
      "scale": 1.0,
      "limits": [-0.43, 0.43]
    },
    "left_hip_roll": {
      "source_landmarks": [23, 24, 25],
      "computation": "plane_angle",
      "scale": 1.0,
      "limits": [-0.43, 0.43]
    },
    "left_hip_pitch": {
      "source_landmarks": [11, 23, 25],
      "computation": "angle_3points",
      "offset": -1.57,
      "scale": 1.0,
      "limits": [-2.53, 2.53]
    },
    "left_knee": {
      "source_landmarks": [23, 25, 27],
      "computation": "angle_3points",
      "offset": 0.0,
      "scale": 1.0,
      "limits": [-0.26, 2.05]
    },
    "left_ankle_pitch": {
      "source_landmarks": [25, 27, 31],
      "computation": "angle_3points",
      "offset": 0.0,
      "scale": 0.5,
      "limits": [-0.87, 0.52]
    },
    "left_ankle_roll": {
      "source_landmarks": [27, 29, 31],
      "computation": "angle_3points",
      "scale": 0.5,
      "limits": [-0.26, 0.26]
    },
    "right_hip_yaw": {
      "source_landmarks": [24, 26],
      "computation": "angle_between_vectors",
      "reference_axis": [0, 0, 1],
      "scale": 1.0,
      "limits": [-0.43, 0.43]
    },
    "right_hip_roll": {
      "source_landmarks": [23, 24, 26],
      "computation": "plane_angle",
      "scale": 1.0,
      "limits": [-0.43, 0.43]
    },
    "right_hip_pitch": {
      "source_landmarks": [12, 24, 26],
      "computation": "angle_3points",
      "offset": -1.57,
      "scale": 1.0,
      "limits": [-2.53, 2.53]
    },
    "right_knee": {
      "source_landmarks": [24, 26, 28],
      "computation": "angle_3points",
      "offset": 0.0,
      "scale": 1.0,
      "limits": [-0.26, 2.05]
    },
    "right_ankle_pitch": {
      "source_landmarks": [26, 28, 32],
      "computation": "angle_3points",
      "offset": 0.0,
      "scale": 0.5,
      "limits": [-0.87, 0.52]
    },
    "right_ankle_roll": {
      "source_landmarks": [28, 30, 32],
      "computation": "angle_3points",
      "scale": 0.5,
      "limits": [-0.26, 0.26]
    },
    "waist_yaw": {
      "source_landmarks": [11, 12, 23, 24],
      "computation": "torso_twist",
      "scale": 0.5,
      "limits": [-2.35, 2.35]
    },
    "waist_roll": {
      "source_landmarks": [11, 12],
      "computation": "shoulder_tilt",
      "scale": 0.5,
      "limits": [-0.52, 0.52]
    },
    "left_shoulder_pitch": {
      "source_landmarks": [11, 13, 15],
      "computation": "angle_3points",
      "offset": 0.0,
      "scale": 1.0,
      "limits": [-2.87, 2.87]
    },
    "left_shoulder_roll": {
      "source_landmarks": [12, 11, 13],
      "computation": "angle_3points",
      "scale": 1.0,
      "limits": [-1.34, 3.11]
    },
    "left_shoulder_yaw": {
      "source_landmarks": [11, 13, 15],
      "computation": "arm_twist",
      "scale": 0.5,
      "limits": [-2.79, 2.79]
    },
    "left_elbow": {
      "source_landmarks": [11, 13, 15],
      "computation": "angle_3points",
      "offset": 0.0,
      "scale": 1.0,
      "limits": [-1.25, 2.61]
    },
    "right_shoulder_pitch": {
      "source_landmarks": [12, 14, 16],
      "computation": "angle_3points",
      "offset": 0.0,
      "scale": 1.0,
      "limits": [-2.87, 2.87]
    },
    "right_shoulder_roll": {
      "source_landmarks": [11, 12, 14],
      "computation": "angle_3points",
      "scale": 1.0,
      "limits": [-3.11, 1.34]
    },
    "right_shoulder_yaw": {
      "source_landmarks": [12, 14, 16],
      "computation": "arm_twist",
      "scale": 0.5,
      "limits": [-2.79, 2.79]
    },
    "right_elbow": {
      "source_landmarks": [12, 14, 16],
      "computation": "angle_3points",
      "offset": 0.0,
      "scale": 1.0,
      "limits": [-2.61, 1.25]
    }
  }
}
```

- [ ] **Step 4: Implement joint map loader**

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
            "source_landmarks": m.source_landmarks,
            "computation": m.computation,
            "scale": m.scale,
            "offset": m.offset,
            "limits": m.limits,
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
            source_landmarks=cfg["source_landmarks"],
            computation=cfg["computation"],
            scale=cfg.get("scale", 1.0),
            offset=cfg.get("offset", 0.0),
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

- [ ] **Step 5: Run test to verify it passes**

```bash
cd packages/skill_foundry
pytest skill_foundry_retarget/tests/test_joint_map.py -v
```

Expected: PASS

- [ ] **Step 6: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_retarget/
git add packages/skill_foundry/skill_foundry_validation/models/g1_description/joint_map.json
git commit -m "feat(retarget): implement joint mapping configuration"
```

---

### Task 2.2: Retargeting Calculator

**Files:**
- Create: `packages/skill_foundry/skill_foundry_retarget/retarget.py`
- Create: `packages/skill_foundry/skill_foundry_retarget/tests/test_retarget.py`

- [ ] **Step 1: Write failing test for retargeting**

```python
# packages/skill_foundry/skill_foundry_retarget/tests/test_retarget.py
import numpy as np
import pytest
from skill_foundry_retarget.retarget import Retargeter

def test_retargeter_outputs_29_joint_angles():
    """Retargeter should output 29 joint angles for G1."""
    retargeter = Retargeter()
    
    # MediaPipe landmarks: 33 points, each (x, y, z)
    landmarks = np.random.rand(33, 3).astype(np.float32)
    
    joint_angles = retargeter.compute(landmarks)
    
    assert joint_angles.shape == (29,)
    assert joint_angles.dtype == np.float32

def test_retargeter_respects_joint_limits():
    """All output angles should be within joint limits."""
    retargeter = Retargeter()
    
    # Extreme landmarks that might produce out-of-limit angles
    landmarks = np.random.rand(33, 3).astype(np.float32) * 10
    
    joint_angles = retargeter.compute(landmarks)
    
    for i, (name, angle) in enumerate(zip(retargeter.joint_names, joint_angles)):
        limits = retargeter.get_limits(name)
        assert limits[0] <= angle <= limits[1], f"{name} out of limits"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/skill_foundry
pytest skill_foundry_retarget/tests/test_retarget.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement retargeting calculator**

```python
# packages/skill_foundry/skill_foundry_retarget/retarget.py
"""Human-to-robot motion retargeting."""

from typing import List, Tuple
import numpy as np

from .joint_map import load_joint_map, JointMap, G1_JOINT_ORDER


def angle_3points(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    """Compute angle at p2 formed by p1-p2-p3."""
    v1 = p1 - p2
    v2 = p3 - p2
    
    v1_norm = np.linalg.norm(v1)
    v2_norm = np.linalg.norm(v2)
    
    if v1_norm < 1e-6 or v2_norm < 1e-6:
        return 0.0
    
    cos_angle = np.dot(v1, v2) / (v1_norm * v2_norm)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    
    return float(np.arccos(cos_angle))


def angle_between_vectors(v1: np.ndarray, ref_axis: np.ndarray) -> float:
    """Compute angle between vector and reference axis."""
    v1_norm = np.linalg.norm(v1)
    ref_norm = np.linalg.norm(ref_axis)
    
    if v1_norm < 1e-6 or ref_norm < 1e-6:
        return 0.0
    
    cos_angle = np.dot(v1, ref_axis) / (v1_norm * ref_norm)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    
    return float(np.arccos(cos_angle))


class Retargeter:
    """Converts human pose landmarks to robot joint angles."""
    
    def __init__(self, joint_map: JointMap = None):
        self.joint_map = joint_map or load_joint_map()
        self.joint_names = G1_JOINT_ORDER
    
    def compute(self, landmarks: np.ndarray) -> np.ndarray:
        """Compute G1 joint angles from MediaPipe landmarks.
        
        Args:
            landmarks: Shape (33, 3) MediaPipe pose landmarks
            
        Returns:
            Shape (29,) joint angles in radians
        """
        angles = np.zeros(29, dtype=np.float32)
        
        for i, joint_name in enumerate(self.joint_names):
            mapping = self.joint_map.get_mapping(joint_name)
            
            if mapping is None:
                angles[i] = 0.0
                continue
            
            angle = self._compute_joint_angle(landmarks, mapping)
            
            # Apply scale and offset
            angle = angle * mapping["scale"] + mapping.get("offset", 0.0)
            
            # Clamp to limits
            limits = mapping["limits"]
            angle = np.clip(angle, limits[0], limits[1])
            
            angles[i] = angle
        
        return angles
    
    def _compute_joint_angle(
        self, landmarks: np.ndarray, mapping: dict
    ) -> float:
        """Compute a single joint angle based on mapping configuration."""
        indices = mapping["source_landmarks"]
        computation = mapping["computation"]
        
        if computation == "angle_3points" and len(indices) >= 3:
            p1 = landmarks[indices[0]]
            p2 = landmarks[indices[1]]
            p3 = landmarks[indices[2]]
            return angle_3points(p1, p2, p3)
        
        elif computation == "angle_between_vectors" and len(indices) >= 2:
            p1 = landmarks[indices[0]]
            p2 = landmarks[indices[1]]
            v = p2 - p1
            ref_axis = np.array(mapping.get("reference_axis", [0, 0, 1]))
            return angle_between_vectors(v, ref_axis)
        
        elif computation == "plane_angle" and len(indices) >= 3:
            # Simplified: use angle_3points
            p1 = landmarks[indices[0]]
            p2 = landmarks[indices[1]]
            p3 = landmarks[indices[2]]
            return angle_3points(p1, p2, p3) - np.pi / 2
        
        elif computation == "torso_twist" and len(indices) >= 4:
            # Angle between shoulder line and hip line projected on XY
            left_shoulder = landmarks[indices[0]]
            right_shoulder = landmarks[indices[1]]
            left_hip = landmarks[indices[2]]
            right_hip = landmarks[indices[3]]
            
            shoulder_vec = right_shoulder[:2] - left_shoulder[:2]
            hip_vec = right_hip[:2] - left_hip[:2]
            
            return angle_between_vectors(
                np.append(shoulder_vec, 0),
                np.append(hip_vec, 0)
            )
        
        elif computation == "shoulder_tilt" and len(indices) >= 2:
            left = landmarks[indices[0]]
            right = landmarks[indices[1]]
            return np.arctan2(right[1] - left[1], right[0] - left[0])
        
        elif computation == "arm_twist":
            return 0.0  # Simplified: arm twist is hard to estimate from 2D
        
        return 0.0
    
    def get_limits(self, joint_name: str) -> Tuple[float, float]:
        """Get joint limits for a named joint."""
        mapping = self.joint_map.get_mapping(joint_name)
        if mapping is None:
            return (-3.14, 3.14)
        return tuple(mapping["limits"])
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd packages/skill_foundry
pytest skill_foundry_retarget/tests/test_retarget.py -v
```

Expected: PASS

- [ ] **Step 5: Commit implementation**

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

### Task 3.1: Camera Capture Hook

**Files:**
- Create: `web/frontend/src/hooks/useCameraCapture.ts`
- Create: `web/frontend/src/hooks/useCameraCapture.test.ts`

- [ ] **Step 1: Write failing test**

```typescript
// web/frontend/src/hooks/useCameraCapture.test.ts
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCameraCapture } from './useCameraCapture';

describe('useCameraCapture', () => {
  it('should initialize with stopped state', () => {
    const { result } = renderHook(() => useCameraCapture());
    
    expect(result.current.isCapturing).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('should provide start and stop functions', () => {
    const { result } = renderHook(() => useCameraCapture());
    
    expect(typeof result.current.startCapture).toBe('function');
    expect(typeof result.current.stopCapture).toBe('function');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web/frontend
npm test -- useCameraCapture.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement camera capture hook**

```typescript
// web/frontend/src/hooks/useCameraCapture.ts
import { useState, useCallback, useRef, useEffect } from 'react';

export interface CameraCaptureState {
  isCapturing: boolean;
  isRecording: boolean;
  error: string | null;
  videoRef: React.RefObject<HTMLVideoElement>;
}

export interface CameraCaptureActions {
  startCapture: () => Promise<void>;
  stopCapture: () => void;
  startRecording: () => void;
  stopRecording: () => void;
  captureFrame: () => Blob | null;
}

export function useCameraCapture(): CameraCaptureState & CameraCaptureActions {
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
        video: { width: 640, height: 480, facingMode: 'user' },
        audio: false,
      });
      
      streamRef.current = stream;
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      
      // Create canvas for frame capture
      canvasRef.current = document.createElement('canvas');
      canvasRef.current.width = 640;
      canvasRef.current.height = 480;
      
      setIsCapturing(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to access camera');
      setIsCapturing(false);
    }
  }, []);

  const stopCapture = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    
    setIsCapturing(false);
    setIsRecording(false);
  }, []);

  const startRecording = useCallback(() => {
    setIsRecording(true);
  }, []);

  const stopRecording = useCallback(() => {
    setIsRecording(false);
  }, []);

  const captureFrame = useCallback((): Blob | null => {
    if (!videoRef.current || !canvasRef.current || !isCapturing) {
      return null;
    }
    
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return null;
    
    ctx.drawImage(videoRef.current, 0, 0);
    
    // Convert to JPEG blob synchronously via data URL
    const dataUrl = canvasRef.current.toDataURL('image/jpeg', 0.8);
    const binary = atob(dataUrl.split(',')[1]);
    const array = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      array[i] = binary.charCodeAt(i);
    }
    return new Blob([array], { type: 'image/jpeg' });
  }, [isCapturing]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  return {
    isCapturing,
    isRecording,
    error,
    videoRef,
    startCapture,
    stopCapture,
    startRecording,
    stopRecording,
    captureFrame,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web/frontend
npm test -- useCameraCapture.test.ts
```

Expected: PASS

- [ ] **Step 5: Commit implementation**

```bash
git add web/frontend/src/hooks/useCameraCapture.ts
git add web/frontend/src/hooks/useCameraCapture.test.ts
git commit -m "feat(frontend): implement camera capture hook"
```

---

### Task 3.2: Motion Capture WebSocket Hook

**Files:**
- Create: `web/frontend/src/hooks/useMotionCaptureWs.ts`

- [ ] **Step 1: Implement WebSocket hook for motion capture**

```typescript
// web/frontend/src/hooks/useMotionCaptureWs.ts
import { useState, useCallback, useRef, useEffect } from 'react';

export interface PoseData {
  landmarks: number[][];  // 33x3 array
  confidence: number;
  timestamp_ms: number;
}

export interface RecordingResult {
  bvh: string;
  duration_sec: number;
  frame_count: number;
}

export interface MotionCaptureWsState {
  isConnected: boolean;
  isRecording: boolean;
  latestPose: PoseData | null;
  error: string | null;
}

export interface MotionCaptureWsActions {
  connect: (url?: string) => void;
  disconnect: () => void;
  sendFrame: (frameBlob: Blob) => void;
  startRecording: () => void;
  stopRecording: () => Promise<RecordingResult | null>;
}

const DEFAULT_WS_URL = 'ws://localhost:8001/ws/capture';

export function useMotionCaptureWs(): MotionCaptureWsState & MotionCaptureWsActions {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [latestPose, setLatestPose] = useState<PoseData | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const recordingPromiseRef = useRef<{
    resolve: (result: RecordingResult | null) => void;
  } | null>(null);

  const connect = useCallback((url: string = DEFAULT_WS_URL) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }
    
    try {
      const ws = new WebSocket(url);
      
      ws.onopen = () => {
        setIsConnected(true);
        setError(null);
      };
      
      ws.onclose = () => {
        setIsConnected(false);
        setIsRecording(false);
      };
      
      ws.onerror = () => {
        setError('WebSocket connection error');
        setIsConnected(false);
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'pose') {
            setLatestPose({
              landmarks: data.landmarks,
              confidence: data.confidence,
              timestamp_ms: data.timestamp_ms,
            });
          } else if (data.type === 'recording_started') {
            setIsRecording(true);
          } else if (data.type === 'recording_stopped') {
            setIsRecording(false);
            if (recordingPromiseRef.current) {
              recordingPromiseRef.current.resolve({
                bvh: data.bvh,
                duration_sec: data.duration_sec,
                frame_count: data.frame_count,
              });
              recordingPromiseRef.current = null;
            }
          }
        } catch {
          // Ignore parse errors
        }
      };
      
      wsRef.current = ws;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect');
    }
  }, []);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setIsRecording(false);
    setLatestPose(null);
  }, []);

  const sendFrame = useCallback((frameBlob: Blob) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      frameBlob.arrayBuffer().then(buffer => {
        wsRef.current?.send(buffer);
      });
    }
  }, []);

  const startRecording = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'start_recording' }));
    }
  }, []);

  const stopRecording = useCallback((): Promise<RecordingResult | null> => {
    return new Promise((resolve) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        resolve(null);
        return;
      }
      
      recordingPromiseRef.current = { resolve };
      wsRef.current.send(JSON.stringify({ type: 'stop_recording' }));
      
      // Timeout after 5 seconds
      setTimeout(() => {
        if (recordingPromiseRef.current) {
          recordingPromiseRef.current.resolve(null);
          recordingPromiseRef.current = null;
        }
      }, 5000);
    });
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    isConnected,
    isRecording,
    latestPose,
    error,
    connect,
    disconnect,
    sendFrame,
    startRecording,
    stopRecording,
  };
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

interface MotionCapturePanelProps {
  onPoseUpdate?: (landmarks: number[][]) => void;
  onRecordingComplete?: (result: RecordingResult) => void;
  motionCaptureUrl?: string;
}

export function MotionCapturePanel({
  onPoseUpdate,
  onRecordingComplete,
  motionCaptureUrl,
}: MotionCapturePanelProps) {
  const { t } = useTranslation();
  
  const camera = useCameraCapture();
  const ws = useMotionCaptureWs();
  
  const frameIntervalRef = useRef<number | null>(null);

  // Stream frames to WebSocket when capturing
  useEffect(() => {
    if (camera.isCapturing && ws.isConnected) {
      frameIntervalRef.current = window.setInterval(() => {
        const frame = camera.captureFrame();
        if (frame) {
          ws.sendFrame(frame);
        }
      }, 33); // ~30 FPS
    }
    
    return () => {
      if (frameIntervalRef.current) {
        clearInterval(frameIntervalRef.current);
        frameIntervalRef.current = null;
      }
    };
  }, [camera.isCapturing, ws.isConnected, camera.captureFrame, ws.sendFrame]);

  // Forward pose updates
  useEffect(() => {
    if (ws.latestPose && onPoseUpdate) {
      onPoseUpdate(ws.latestPose.landmarks);
    }
  }, [ws.latestPose, onPoseUpdate]);

  const handleStartCapture = useCallback(async () => {
    await camera.startCapture();
    ws.connect(motionCaptureUrl);
  }, [camera.startCapture, ws.connect, motionCaptureUrl]);

  const handleStopCapture = useCallback(() => {
    camera.stopCapture();
    ws.disconnect();
  }, [camera.stopCapture, ws.disconnect]);

  const handleStartRecording = useCallback(() => {
    ws.startRecording();
  }, [ws.startRecording]);

  const handleStopRecording = useCallback(async () => {
    const result = await ws.stopRecording();
    if (result && onRecordingComplete) {
      onRecordingComplete(result);
    }
  }, [ws.stopRecording, onRecordingComplete]);

  return (
    <div className="motion-capture-panel">
      <div className="video-container">
        <video
          ref={camera.videoRef}
          autoPlay
          playsInline
          muted
          style={{ width: '100%', maxWidth: 640, background: '#000' }}
        />
        
        {ws.latestPose && (
          <div className="pose-confidence">
            {t('motionCapture.confidence')}: {(ws.latestPose.confidence * 100).toFixed(0)}%
          </div>
        )}
      </div>
      
      <div className="controls">
        {!camera.isCapturing ? (
          <button onClick={handleStartCapture} className="btn-primary">
            {t('motionCapture.startCamera')}
          </button>
        ) : (
          <>
            <button onClick={handleStopCapture} className="btn-secondary">
              {t('motionCapture.stopCamera')}
            </button>
            
            {!ws.isRecording ? (
              <button
                onClick={handleStartRecording}
                className="btn-record"
                disabled={!ws.isConnected}
              >
                {t('motionCapture.startRecording')}
              </button>
            ) : (
              <button onClick={handleStopRecording} className="btn-stop-record">
                {t('motionCapture.stopRecording')}
              </button>
            )}
          </>
        )}
      </div>
      
      {(camera.error || ws.error) && (
        <div className="error-message">
          {camera.error || ws.error}
        </div>
      )}
      
      <div className="status">
        <span className={ws.isConnected ? 'connected' : 'disconnected'}>
          {ws.isConnected ? t('motionCapture.connected') : t('motionCapture.disconnected')}
        </span>
        {ws.isRecording && (
          <span className="recording-indicator">
            {t('motionCapture.recording')}
          </span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add i18n translations**

Add to `web/frontend/src/locales/en.json`:

```json
{
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
}
```

- [ ] **Step 3: Commit implementation**

```bash
git add web/frontend/src/components/MotionCapturePanel.tsx
git add web/frontend/src/locales/en.json
git commit -m "feat(frontend): implement motion capture panel component"
```

---

### Task 3.4: Integrate with Pose Studio

**Files:**
- Modify: `web/frontend/src/pages/PoseStudio.tsx`

- [ ] **Step 1: Add motion capture mode to Pose Studio**

Add imports and state at the top of PoseStudio.tsx:

```typescript
import { MotionCapturePanel } from '../components/MotionCapturePanel';
import { Retargeter } from '../lib/retargeter';  // Will create next

// Add to component state
const [liveTrackMode, setLiveTrackMode] = useState(false);
const retargeterRef = useRef(new Retargeter());
```

Add handler for pose updates:

```typescript
const handlePoseUpdate = useCallback((landmarks: number[][]) => {
  if (!liveTrackMode) return;
  
  const jointAngles = retargeterRef.current.compute(landmarks);
  // Update wasmJointRad state with computed angles
  setWasmJointRad(prev => {
    const next = { ...prev };
    jointAngles.forEach((angle, idx) => {
      const jointName = JOINT_ORDER[idx];
      if (jointName && jointName in next) {
        next[jointName] = angle;
      }
    });
    return next;
  });
}, [liveTrackMode]);
```

Add UI toggle and panel in the render:

```tsx
{/* Add in sidebar or as a collapsible section */}
<div className="live-track-section">
  <label>
    <input
      type="checkbox"
      checked={liveTrackMode}
      onChange={(e) => setLiveTrackMode(e.target.checked)}
    />
    {t('poseStudio.liveTrackMode')}
  </label>
  
  {liveTrackMode && (
    <MotionCapturePanel
      onPoseUpdate={handlePoseUpdate}
      onRecordingComplete={(result) => {
        // Handle BVH result - could save or convert to keyframes
        console.log('Recording complete:', result);
      }}
    />
  )}
</div>
```

- [ ] **Step 2: Commit integration**

```bash
git add web/frontend/src/pages/PoseStudio.tsx
git commit -m "feat(frontend): integrate motion capture with Pose Studio"
```

---

## Phase 4: AMP RL Training Pipeline

**Objective:** Create training scripts that use Adversarial Motion Priors to train policies that imitate captured motion.

**Location:** `packages/skill_foundry/skill_foundry_rl/`

### Task 4.1: Reference Motion Loader

**Files:**
- Create: `packages/skill_foundry/skill_foundry_rl/reference_motion.py`
- Create: `packages/skill_foundry/skill_foundry_rl/tests/test_reference_motion.py`

- [ ] **Step 1: Write failing test**

```python
# packages/skill_foundry/skill_foundry_rl/tests/test_reference_motion.py
import numpy as np
import pytest
from skill_foundry_rl.reference_motion import ReferenceMotion, load_reference_motion

def test_reference_motion_loads_from_json():
    """ReferenceMotion should load from trajectory JSON."""
    trajectory = {
        "version": "1.0",
        "robot": "unitree_g1_29dof",
        "joint_order": ["left_hip_yaw", "left_hip_roll"],
        "dt": 0.02,
        "frames": [
            {"joint_angles_rad": [0.0, 0.0]},
            {"joint_angles_rad": [0.1, 0.1]},
        ]
    }
    
    motion = ReferenceMotion.from_dict(trajectory)
    
    assert motion.num_frames == 2
    assert motion.dt == 0.02
    assert motion.duration == pytest.approx(0.02)

def test_reference_motion_samples_at_time():
    """ReferenceMotion should interpolate at arbitrary time."""
    trajectory = {
        "version": "1.0",
        "dt": 0.1,
        "frames": [
            {"joint_angles_rad": [0.0]},
            {"joint_angles_rad": [1.0]},
        ]
    }
    
    motion = ReferenceMotion.from_dict(trajectory)
    
    # Sample at midpoint
    angles = motion.sample(0.05)
    assert angles[0] == pytest.approx(0.5, rel=0.01)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/skill_foundry
pytest skill_foundry_rl/tests/test_reference_motion.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement reference motion loader**

```python
# packages/skill_foundry/skill_foundry_rl/reference_motion.py
"""Reference motion loading and sampling for AMP training."""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np


class ReferenceMotion:
    """Holds reference motion data and provides time-based sampling."""
    
    def __init__(
        self,
        frames: np.ndarray,
        dt: float,
        joint_order: List[str],
    ):
        """Initialize reference motion.
        
        Args:
            frames: Shape (num_frames, num_joints) joint angles in radians
            dt: Time step between frames in seconds
            joint_order: List of joint names in order
        """
        self.frames = frames
        self.dt = dt
        self.joint_order = joint_order
    
    @property
    def num_frames(self) -> int:
        return self.frames.shape[0]
    
    @property
    def num_joints(self) -> int:
        return self.frames.shape[1]
    
    @property
    def duration(self) -> float:
        return (self.num_frames - 1) * self.dt
    
    def sample(self, t: float) -> np.ndarray:
        """Sample joint angles at time t with linear interpolation.
        
        Args:
            t: Time in seconds from start of motion
            
        Returns:
            Joint angles at time t
        """
        if self.num_frames == 1:
            return self.frames[0].copy()
        
        # Clamp to valid range
        t = np.clip(t, 0.0, self.duration)
        
        # Find frame indices
        frame_idx = t / self.dt
        idx0 = int(np.floor(frame_idx))
        idx1 = min(idx0 + 1, self.num_frames - 1)
        
        # Interpolation weight
        alpha = frame_idx - idx0
        
        return (1 - alpha) * self.frames[idx0] + alpha * self.frames[idx1]
    
    def sample_batch(self, times: np.ndarray) -> np.ndarray:
        """Sample joint angles at multiple times.
        
        Args:
            times: Array of times in seconds
            
        Returns:
            Shape (len(times), num_joints) joint angles
        """
        return np.array([self.sample(t) for t in times])
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReferenceMotion":
        """Create ReferenceMotion from trajectory dict."""
        frames_data = data.get("frames", [])
        dt = data.get("dt", 0.02)
        joint_order = data.get("joint_order", [])
        
        if not frames_data:
            raise ValueError("No frames in trajectory data")
        
        # Extract joint angles from frames
        frames = np.array([
            f.get("joint_angles_rad", f.get("q", []))
            for f in frames_data
        ], dtype=np.float32)
        
        return cls(frames=frames, dt=dt, joint_order=joint_order)
    
    @classmethod
    def from_json(cls, path: Path) -> "ReferenceMotion":
        """Load ReferenceMotion from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


def load_reference_motion(path: Path) -> ReferenceMotion:
    """Load reference motion from file.
    
    Args:
        path: Path to reference trajectory JSON
        
    Returns:
        ReferenceMotion instance
    """
    return ReferenceMotion.from_json(path)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd packages/skill_foundry
pytest skill_foundry_rl/tests/test_reference_motion.py -v
```

Expected: PASS

- [ ] **Step 5: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_rl/reference_motion.py
git add packages/skill_foundry/skill_foundry_rl/tests/test_reference_motion.py
git commit -m "feat(rl): implement reference motion loader for AMP"
```

---

### Task 4.2: AMP Discriminator

**Files:**
- Create: `packages/skill_foundry/skill_foundry_rl/amp_discriminator.py`
- Create: `packages/skill_foundry/skill_foundry_rl/tests/test_amp_discriminator.py`

- [ ] **Step 1: Write failing test**

```python
# packages/skill_foundry/skill_foundry_rl/tests/test_amp_discriminator.py
import numpy as np
import pytest
import torch
from skill_foundry_rl.amp_discriminator import AMPDiscriminator

def test_discriminator_outputs_scores():
    """Discriminator should output scores for state transitions."""
    disc = AMPDiscriminator(state_dim=29, hidden_dim=256)
    
    # Batch of state transitions: (current_state, next_state)
    batch_size = 32
    states = torch.randn(batch_size, 29)
    next_states = torch.randn(batch_size, 29)
    
    scores = disc(states, next_states)
    
    assert scores.shape == (batch_size, 1)

def test_discriminator_reward_is_bounded():
    """AMP reward should be bounded and positive for expert-like motion."""
    disc = AMPDiscriminator(state_dim=29, hidden_dim=256)
    
    states = torch.randn(16, 29)
    next_states = torch.randn(16, 29)
    
    rewards = disc.compute_reward(states, next_states)
    
    assert rewards.shape == (16,)
    # Rewards should be finite
    assert torch.isfinite(rewards).all()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/skill_foundry
pytest skill_foundry_rl/tests/test_amp_discriminator.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement AMP discriminator**

```python
# packages/skill_foundry/skill_foundry_rl/amp_discriminator.py
"""Adversarial Motion Prior discriminator for motion imitation."""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple


class AMPDiscriminator(nn.Module):
    """Discriminator network for Adversarial Motion Priors.
    
    Learns to distinguish between expert (reference) motion and
    policy-generated motion based on state transitions.
    """
    
    def __init__(
        self,
        state_dim: int,
        hidden_dim: int = 256,
        num_layers: int = 2,
    ):
        """Initialize discriminator.
        
        Args:
            state_dim: Dimension of state (joint angles)
            hidden_dim: Hidden layer dimension
            num_layers: Number of hidden layers
        """
        super().__init__()
        
        # Input: concatenation of current and next state
        input_dim = state_dim * 2
        
        layers = []
        layers.append(nn.Linear(input_dim, hidden_dim))
        layers.append(nn.ReLU())
        
        for _ in range(num_layers - 1):
            layers.append(nn.Linear(hidden_dim, hidden_dim))
            layers.append(nn.ReLU())
        
        layers.append(nn.Linear(hidden_dim, 1))
        
        self.net = nn.Sequential(*layers)
        
        # Gradient penalty coefficient
        self.grad_penalty_coef = 10.0
    
    def forward(
        self,
        states: torch.Tensor,
        next_states: torch.Tensor,
    ) -> torch.Tensor:
        """Compute discriminator scores.
        
        Args:
            states: Current states, shape (batch, state_dim)
            next_states: Next states, shape (batch, state_dim)
            
        Returns:
            Discriminator scores, shape (batch, 1)
        """
        x = torch.cat([states, next_states], dim=-1)
        return self.net(x)
    
    def compute_reward(
        self,
        states: torch.Tensor,
        next_states: torch.Tensor,
    ) -> torch.Tensor:
        """Compute AMP reward for policy training.
        
        Uses the discriminator output to compute a reward that
        encourages the policy to produce expert-like motion.
        
        Args:
            states: Current states
            next_states: Next states
            
        Returns:
            Reward values, shape (batch,)
        """
        with torch.no_grad():
            scores = self.forward(states, next_states)
            # Reward = -log(1 - sigmoid(D(s, s')))
            # This encourages high discriminator scores (expert-like)
            rewards = -torch.log(1 - torch.sigmoid(scores) + 1e-8)
            return rewards.squeeze(-1)
    
    def compute_loss(
        self,
        expert_states: torch.Tensor,
        expert_next_states: torch.Tensor,
        policy_states: torch.Tensor,
        policy_next_states: torch.Tensor,
    ) -> Tuple[torch.Tensor, dict]:
        """Compute discriminator loss with gradient penalty.
        
        Args:
            expert_states: Expert current states
            expert_next_states: Expert next states
            policy_states: Policy current states
            policy_next_states: Policy next states
            
        Returns:
            Tuple of (loss, metrics dict)
        """
        # Expert should have high scores (label 1)
        expert_scores = self.forward(expert_states, expert_next_states)
        expert_loss = F.binary_cross_entropy_with_logits(
            expert_scores,
            torch.ones_like(expert_scores),
        )
        
        # Policy should have low scores (label 0)
        policy_scores = self.forward(policy_states, policy_next_states)
        policy_loss = F.binary_cross_entropy_with_logits(
            policy_scores,
            torch.zeros_like(policy_scores),
        )
        
        # Gradient penalty for stability
        grad_penalty = self._gradient_penalty(
            expert_states, expert_next_states,
            policy_states, policy_next_states,
        )
        
        total_loss = expert_loss + policy_loss + self.grad_penalty_coef * grad_penalty
        
        metrics = {
            "disc_expert_loss": expert_loss.item(),
            "disc_policy_loss": policy_loss.item(),
            "disc_grad_penalty": grad_penalty.item(),
            "disc_expert_score": expert_scores.mean().item(),
            "disc_policy_score": policy_scores.mean().item(),
        }
        
        return total_loss, metrics
    
    def _gradient_penalty(
        self,
        expert_states: torch.Tensor,
        expert_next_states: torch.Tensor,
        policy_states: torch.Tensor,
        policy_next_states: torch.Tensor,
    ) -> torch.Tensor:
        """Compute gradient penalty for WGAN-GP style training."""
        batch_size = expert_states.shape[0]
        
        # Interpolate between expert and policy
        alpha = torch.rand(batch_size, 1, device=expert_states.device)
        
        interp_states = alpha * expert_states + (1 - alpha) * policy_states
        interp_next = alpha * expert_next_states + (1 - alpha) * policy_next_states
        
        interp_states.requires_grad_(True)
        interp_next.requires_grad_(True)
        
        scores = self.forward(interp_states, interp_next)
        
        gradients = torch.autograd.grad(
            outputs=scores,
            inputs=[interp_states, interp_next],
            grad_outputs=torch.ones_like(scores),
            create_graph=True,
            retain_graph=True,
        )
        
        grad_norm = torch.sqrt(
            gradients[0].pow(2).sum(dim=-1) +
            gradients[1].pow(2).sum(dim=-1) +
            1e-8
        )
        
        penalty = ((grad_norm - 1) ** 2).mean()
        return penalty
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd packages/skill_foundry
pytest skill_foundry_rl/tests/test_amp_discriminator.py -v
```

Expected: PASS

- [ ] **Step 5: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_rl/amp_discriminator.py
git add packages/skill_foundry/skill_foundry_rl/tests/test_amp_discriminator.py
git commit -m "feat(rl): implement AMP discriminator for motion imitation"
```

---

### Task 4.3: Motion Training Script

**Files:**
- Create: `packages/skill_foundry/skill_foundry_rl/train_motion.py`

- [ ] **Step 1: Implement motion training script**

```python
# packages/skill_foundry/skill_foundry_rl/train_motion.py
"""Training script for motion imitation with AMP."""

import argparse
import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.optim import Adam

from .g1_tracking_env import G1TrackingEnv
from .reference_motion import load_reference_motion, ReferenceMotion
from .amp_discriminator import AMPDiscriminator
from .ppo_train import PPOAgent, PPOConfig

logger = logging.getLogger(__name__)


class AMPTrainer:
    """Trainer for motion imitation using AMP + PPO."""
    
    def __init__(
        self,
        env: G1TrackingEnv,
        reference_motion: ReferenceMotion,
        config: Optional[dict] = None,
    ):
        self.env = env
        self.reference_motion = reference_motion
        self.config = config or {}
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Initialize discriminator
        state_dim = env.observation_space.shape[0]
        self.discriminator = AMPDiscriminator(
            state_dim=29,  # Joint angles only for AMP
            hidden_dim=self.config.get("disc_hidden_dim", 256),
        ).to(self.device)
        
        self.disc_optimizer = Adam(
            self.discriminator.parameters(),
            lr=self.config.get("disc_lr", 1e-4),
        )
        
        # Initialize PPO agent
        ppo_config = PPOConfig(
            learning_rate=self.config.get("ppo_lr", 3e-4),
            gamma=self.config.get("gamma", 0.99),
            gae_lambda=self.config.get("gae_lambda", 0.95),
            clip_range=self.config.get("clip_range", 0.2),
            n_epochs=self.config.get("n_epochs", 10),
        )
        self.ppo_agent = PPOAgent(env, ppo_config)
        
        # AMP reward weight
        self.amp_reward_weight = self.config.get("amp_reward_weight", 0.5)
        
        # Expert buffer for discriminator training
        self.expert_buffer = []
        self._fill_expert_buffer()
    
    def _fill_expert_buffer(self, num_samples: int = 10000):
        """Fill buffer with expert state transitions from reference motion."""
        dt = self.reference_motion.dt
        duration = self.reference_motion.duration
        
        for _ in range(num_samples):
            t = np.random.uniform(0, duration - dt)
            state = self.reference_motion.sample(t)
            next_state = self.reference_motion.sample(t + dt)
            self.expert_buffer.append((state, next_state))
    
    def _sample_expert_batch(self, batch_size: int):
        """Sample a batch of expert transitions."""
        indices = np.random.choice(len(self.expert_buffer), batch_size)
        states = []
        next_states = []
        for idx in indices:
            s, ns = self.expert_buffer[idx]
            states.append(s)
            next_states.append(ns)
        return (
            torch.tensor(np.array(states), dtype=torch.float32, device=self.device),
            torch.tensor(np.array(next_states), dtype=torch.float32, device=self.device),
        )
    
    def train(
        self,
        total_timesteps: int,
        log_interval: int = 1000,
        save_interval: int = 10000,
        save_path: Optional[Path] = None,
    ):
        """Run AMP training loop.
        
        Args:
            total_timesteps: Total environment steps
            log_interval: Steps between logging
            save_interval: Steps between checkpoints
            save_path: Directory to save checkpoints
        """
        obs = self.env.reset()
        episode_reward = 0
        episode_length = 0
        
        policy_buffer = []  # Buffer for discriminator training
        
        for step in range(total_timesteps):
            # Get action from policy
            action, log_prob, value = self.ppo_agent.get_action(obs)
            
            # Step environment
            next_obs, task_reward, done, info = self.env.step(action)
            
            # Compute AMP reward
            obs_joints = torch.tensor(
                obs[:29], dtype=torch.float32, device=self.device
            ).unsqueeze(0)
            next_obs_joints = torch.tensor(
                next_obs[:29], dtype=torch.float32, device=self.device
            ).unsqueeze(0)
            
            amp_reward = self.discriminator.compute_reward(
                obs_joints, next_obs_joints
            ).item()
            
            # Combined reward
            total_reward = (
                (1 - self.amp_reward_weight) * task_reward +
                self.amp_reward_weight * amp_reward
            )
            
            # Store transition for PPO
            self.ppo_agent.store_transition(
                obs, action, total_reward, done, log_prob, value
            )
            
            # Store for discriminator
            policy_buffer.append((obs[:29].copy(), next_obs[:29].copy()))
            
            episode_reward += total_reward
            episode_length += 1
            
            if done:
                obs = self.env.reset()
                logger.info(
                    f"Step {step}: episode_reward={episode_reward:.2f}, "
                    f"length={episode_length}"
                )
                episode_reward = 0
                episode_length = 0
            else:
                obs = next_obs
            
            # Update discriminator periodically
            if len(policy_buffer) >= 256:
                self._update_discriminator(policy_buffer)
                policy_buffer = []
            
            # Update PPO
            if step > 0 and step % self.ppo_agent.config.n_steps == 0:
                self.ppo_agent.update()
            
            # Logging
            if step > 0 and step % log_interval == 0:
                logger.info(f"Step {step}/{total_timesteps}")
            
            # Save checkpoint
            if save_path and step > 0 and step % save_interval == 0:
                self.save_checkpoint(save_path / f"checkpoint_{step}.pt")
    
    def _update_discriminator(self, policy_buffer):
        """Update discriminator with expert and policy samples."""
        batch_size = min(len(policy_buffer), 256)
        
        # Sample expert batch
        expert_states, expert_next = self._sample_expert_batch(batch_size)
        
        # Policy batch
        indices = np.random.choice(len(policy_buffer), batch_size)
        policy_states = torch.tensor(
            np.array([policy_buffer[i][0] for i in indices]),
            dtype=torch.float32, device=self.device
        )
        policy_next = torch.tensor(
            np.array([policy_buffer[i][1] for i in indices]),
            dtype=torch.float32, device=self.device
        )
        
        # Update
        self.disc_optimizer.zero_grad()
        loss, metrics = self.discriminator.compute_loss(
            expert_states, expert_next,
            policy_states, policy_next,
        )
        loss.backward()
        self.disc_optimizer.step()
        
        logger.debug(f"Discriminator update: {metrics}")
    
    def save_checkpoint(self, path: Path):
        """Save training checkpoint."""
        torch.save({
            "discriminator": self.discriminator.state_dict(),
            "disc_optimizer": self.disc_optimizer.state_dict(),
            "ppo_agent": self.ppo_agent.state_dict(),
        }, path)
        logger.info(f"Saved checkpoint to {path}")


def main():
    """Entry point for motion training."""
    parser = argparse.ArgumentParser(description="Train motion imitation policy")
    parser.add_argument(
        "--reference-trajectory",
        type=Path,
        required=True,
        help="Path to reference trajectory JSON",
    )
    parser.add_argument(
        "--mjcf-path",
        type=Path,
        required=True,
        help="Path to MuJoCo XML model",
    )
    parser.add_argument(
        "--total-timesteps",
        type=int,
        default=1_000_000,
        help="Total training timesteps",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./output"),
        help="Output directory for checkpoints",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional JSON config file",
    )
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    # Load config
    config = {}
    if args.config:
        with open(args.config) as f:
            config = json.load(f)
    
    # Load reference motion
    reference_motion = load_reference_motion(args.reference_trajectory)
    logger.info(
        f"Loaded reference motion: {reference_motion.num_frames} frames, "
        f"{reference_motion.duration:.2f}s duration"
    )
    
    # Create environment
    env = G1TrackingEnv(
        mjcf_path=str(args.mjcf_path),
        reference_trajectory_path=str(args.reference_trajectory),
    )
    
    # Create trainer
    trainer = AMPTrainer(env, reference_motion, config)
    
    # Train
    args.output_dir.mkdir(parents=True, exist_ok=True)
    trainer.train(
        total_timesteps=args.total_timesteps,
        save_path=args.output_dir,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add entry point to pyproject.toml**

Add to `packages/skill_foundry/pyproject.toml` under `[project.scripts]`:

```toml
skill-foundry-train-motion = "skill_foundry_rl.train_motion:main"
```

- [ ] **Step 3: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_rl/train_motion.py
git add packages/skill_foundry/pyproject.toml
git commit -m "feat(rl): implement AMP motion training script"
```

---

## Phase 5: Eval & Export Extensions

**Objective:** Add motion-specific evaluation metrics and export capabilities.

### Task 5.1: Motion Imitation Score

**Files:**
- Create: `packages/skill_foundry/skill_foundry_rl/motion_eval.py`

- [ ] **Step 1: Implement motion evaluation**

```python
# packages/skill_foundry/skill_foundry_rl/motion_eval.py
"""Evaluation metrics for motion imitation policies."""

import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

from .reference_motion import ReferenceMotion, load_reference_motion


def compute_motion_imitation_score(
    policy_trajectory: np.ndarray,
    reference_motion: ReferenceMotion,
    dt: float,
) -> Dict[str, float]:
    """Compute motion imitation quality metrics.
    
    Args:
        policy_trajectory: Shape (num_steps, num_joints) policy joint angles
        reference_motion: Reference motion to compare against
        dt: Time step of policy trajectory
        
    Returns:
        Dict of metric names to values
    """
    num_steps = policy_trajectory.shape[0]
    
    # Sample reference at same times as policy
    times = np.arange(num_steps) * dt
    reference_samples = reference_motion.sample_batch(times)
    
    # Ensure shapes match
    min_joints = min(policy_trajectory.shape[1], reference_samples.shape[1])
    policy_traj = policy_trajectory[:, :min_joints]
    ref_traj = reference_samples[:, :min_joints]
    
    # Mean squared error
    mse = np.mean((policy_traj - ref_traj) ** 2)
    
    # Per-joint RMSE
    per_joint_rmse = np.sqrt(np.mean((policy_traj - ref_traj) ** 2, axis=0))
    
    # Maximum deviation
    max_deviation = np.max(np.abs(policy_traj - ref_traj))
    
    # Correlation coefficient (averaged over joints)
    correlations = []
    for j in range(min_joints):
        if np.std(ref_traj[:, j]) > 1e-6 and np.std(policy_traj[:, j]) > 1e-6:
            corr = np.corrcoef(policy_traj[:, j], ref_traj[:, j])[0, 1]
            if np.isfinite(corr):
                correlations.append(corr)
    mean_correlation = np.mean(correlations) if correlations else 0.0
    
    # Motion imitation score (0-100, higher is better)
    # Based on RMSE with exponential scaling
    rmse = np.sqrt(mse)
    imitation_score = 100 * np.exp(-5 * rmse)
    
    return {
        "motion_imitation_score": float(imitation_score),
        "mse": float(mse),
        "rmse": float(rmse),
        "max_deviation_rad": float(max_deviation),
        "mean_correlation": float(mean_correlation),
        "per_joint_rmse": per_joint_rmse.tolist(),
    }


def evaluate_motion_policy(
    policy_path: Path,
    reference_trajectory_path: Path,
    mjcf_path: Path,
    num_episodes: int = 10,
    max_steps: int = 1000,
) -> Dict[str, Any]:
    """Run full evaluation of a motion imitation policy.
    
    Args:
        policy_path: Path to policy checkpoint
        reference_trajectory_path: Path to reference trajectory
        mjcf_path: Path to MuJoCo model
        num_episodes: Number of evaluation episodes
        max_steps: Maximum steps per episode
        
    Returns:
        Evaluation results dict
    """
    from .g1_tracking_env import G1TrackingEnv
    import torch
    
    # Load reference motion
    reference_motion = load_reference_motion(reference_trajectory_path)
    
    # Create environment
    env = G1TrackingEnv(
        mjcf_path=str(mjcf_path),
        reference_trajectory_path=str(reference_trajectory_path),
    )
    
    # Load policy
    checkpoint = torch.load(policy_path, map_location="cpu")
    # Assuming PPO agent structure
    # policy = ... (load from checkpoint)
    
    all_scores = []
    all_lengths = []
    all_rewards = []
    
    for ep in range(num_episodes):
        obs = env.reset()
        trajectory = []
        episode_reward = 0
        
        for step in range(max_steps):
            # Get action from policy (simplified - actual implementation depends on policy format)
            action = np.zeros(env.action_space.shape)  # Placeholder
            
            obs, reward, done, info = env.step(action)
            trajectory.append(obs[:29].copy())  # Joint angles
            episode_reward += reward
            
            if done:
                break
        
        trajectory = np.array(trajectory)
        
        # Compute imitation score
        scores = compute_motion_imitation_score(
            trajectory,
            reference_motion,
            env.dt,
        )
        
        all_scores.append(scores["motion_imitation_score"])
        all_lengths.append(len(trajectory))
        all_rewards.append(episode_reward)
    
    return {
        "mean_imitation_score": float(np.mean(all_scores)),
        "std_imitation_score": float(np.std(all_scores)),
        "mean_episode_length": float(np.mean(all_lengths)),
        "mean_episode_reward": float(np.mean(all_rewards)),
        "num_episodes": num_episodes,
    }
```

- [ ] **Step 2: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_rl/motion_eval.py
git commit -m "feat(rl): implement motion imitation evaluation metrics"
```

---

### Task 5.2: Motion Skill Bundle Extension

**Files:**
- Modify: `packages/skill_foundry/skill_foundry_export/packaging.py`

- [ ] **Step 1: Extend packaging for motion skills**

Add to existing `packaging.py`:

```python
def create_motion_skill_bundle(
    policy_path: Path,
    reference_trajectory_path: Path,
    joint_map_path: Path,
    output_path: Path,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """Create a motion skill bundle with all required artifacts.
    
    Args:
        policy_path: Path to trained policy checkpoint
        reference_trajectory_path: Path to reference trajectory
        joint_map_path: Path to joint mapping configuration
        output_path: Output path for the bundle
        metadata: Optional additional metadata
        
    Returns:
        Path to created bundle
    """
    import shutil
    import hashlib
    
    bundle_dir = output_path.with_suffix("")
    bundle_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy policy
    policy_dest = bundle_dir / "policy.pt"
    shutil.copy(policy_path, policy_dest)
    
    # Export to ONNX if possible
    try:
        from .onnx_export import export_policy_to_onnx
        onnx_path = bundle_dir / "policy.onnx"
        export_policy_to_onnx(policy_path, onnx_path)
    except Exception as e:
        logging.warning(f"ONNX export failed: {e}")
    
    # Copy joint map
    joint_map_dest = bundle_dir / "joint_map.json"
    shutil.copy(joint_map_path, joint_map_dest)
    
    # Copy reference trajectory (optional, for debugging)
    ref_dest = bundle_dir / "reference_preview.json"
    shutil.copy(reference_trajectory_path, ref_dest)
    
    # Load reference for metadata
    with open(reference_trajectory_path) as f:
        ref_data = json.load(f)
    
    # Compute hashes
    with open(policy_path, "rb") as f:
        policy_hash = hashlib.sha256(f.read()).hexdigest()
    with open(reference_trajectory_path, "rb") as f:
        ref_hash = hashlib.sha256(f.read()).hexdigest()
    
    # Create motion metadata
    motion_meta = {
        "type": "motion_skill",
        "motion_name": metadata.get("motion_name", "unnamed_motion") if metadata else "unnamed_motion",
        "duration_sec": (len(ref_data.get("frames", [])) - 1) * ref_data.get("dt", 0.02),
        "frame_count": len(ref_data.get("frames", [])),
        "target_robot": ref_data.get("robot", "unitree_g1_29dof"),
        "reference_hash": ref_hash,
        "source": "video_to_motion",
    }
    
    with open(bundle_dir / "motion_meta.json", "w") as f:
        json.dump(motion_meta, f, indent=2)
    
    # Create manifest
    manifest = {
        "version": "1.0",
        "type": "motion_skill_bundle",
        "artifacts": {
            "policy": "policy.pt",
            "policy_onnx": "policy.onnx" if (bundle_dir / "policy.onnx").exists() else None,
            "joint_map": "joint_map.json",
            "motion_meta": "motion_meta.json",
            "reference_preview": "reference_preview.json",
        },
        "hashes": {
            "policy": policy_hash,
            "reference": ref_hash,
        },
        "metadata": metadata or {},
    }
    
    with open(bundle_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    
    # Create zip archive
    shutil.make_archive(str(output_path.with_suffix("")), "zip", bundle_dir)
    
    # Rename to .skillbundle
    final_path = output_path.with_suffix(".skillbundle")
    shutil.move(str(output_path.with_suffix("")) + ".zip", final_path)
    
    # Cleanup temp dir
    shutil.rmtree(bundle_dir)
    
    return final_path
```

- [ ] **Step 2: Commit implementation**

```bash
git add packages/skill_foundry/skill_foundry_export/packaging.py
git commit -m "feat(export): extend packaging for motion skill bundles"
```

---

## Phase 6: End-to-End Integration

**Objective:** Wire everything together for the complete Video-to-Motion workflow.

### Task 6.1: Backend API Endpoints

**Files:**
- Modify: `web/backend/app/main.py`
- Create: `web/backend/app/services/motion_capture.py`

- [ ] **Step 1: Add motion capture API endpoints**

```python
# web/backend/app/services/motion_capture.py
"""Motion capture service integration."""

import asyncio
import json
from pathlib import Path
from typing import Optional
import aiohttp

MOTION_CAPTURE_URL = "http://localhost:8001"


async def submit_bvh_for_training(
    bvh_content: str,
    motion_name: str,
    user_id: str,
) -> dict:
    """Submit BVH content to start training pipeline.
    
    Args:
        bvh_content: BVH file content
        motion_name: Name for the motion
        user_id: User identifier
        
    Returns:
        Job submission result
    """
    from .pipeline import create_training_job
    
    # Save BVH to workspace
    workspace_dir = Path(f"data/platform/users/{user_id}/motions")
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    bvh_path = workspace_dir / f"{motion_name}.bvh"
    with open(bvh_path, "w") as f:
        f.write(bvh_content)
    
    # Convert BVH to reference trajectory
    from skill_foundry_retarget.bvh_to_trajectory import BVHToTrajectoryConverter
    
    converter = BVHToTrajectoryConverter()
    trajectory = converter.convert(bvh_content)
    
    trajectory_path = workspace_dir / f"{motion_name}_trajectory.json"
    with open(trajectory_path, "w") as f:
        json.dump(trajectory, f)
    
    # Create training job
    job = await create_training_job(
        user_id=user_id,
        job_type="motion_training",
        config={
            "reference_trajectory": str(trajectory_path),
            "motion_name": motion_name,
        },
    )
    
    return {
        "job_id": job["id"],
        "status": "queued",
        "motion_name": motion_name,
    }
```

Add to `web/backend/app/main.py`:

```python
from fastapi import APIRouter
from pydantic import BaseModel

motion_router = APIRouter(prefix="/api/motion", tags=["motion"])

class SubmitMotionRequest(BaseModel):
    bvh_content: str
    motion_name: str

@motion_router.post("/submit")
async def submit_motion(
    request: SubmitMotionRequest,
    user_id: str = Header(None, alias="X-User-Id"),
):
    """Submit captured motion for training."""
    from app.services.motion_capture import submit_bvh_for_training
    
    user_id = user_id or os.getenv("G1_DEV_USER_ID", "dev-user")
    
    result = await submit_bvh_for_training(
        bvh_content=request.bvh_content,
        motion_name=request.motion_name,
        user_id=user_id,
    )
    
    return result

# Add router to app
app.include_router(motion_router)
```

- [ ] **Step 2: Commit implementation**

```bash
git add web/backend/app/services/motion_capture.py
git add web/backend/app/main.py
git commit -m "feat(backend): add motion capture API endpoints"
```

---

### Task 6.2: Frontend Training Submission

**Files:**
- Create: `web/frontend/src/api/motionCapture.ts`
- Modify: `web/frontend/src/components/MotionCapturePanel.tsx`

- [ ] **Step 1: Add API client for motion submission**

```typescript
// web/frontend/src/api/motionCapture.ts
import { apiFetch } from './client';

export interface SubmitMotionResponse {
  job_id: string;
  status: string;
  motion_name: string;
}

export async function submitMotionForTraining(
  bvhContent: string,
  motionName: string,
): Promise<SubmitMotionResponse> {
  const response = await apiFetch('/api/motion/submit', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      bvh_content: bvhContent,
      motion_name: motionName,
    }),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to submit motion: ${response.statusText}`);
  }
  
  return response.json();
}

export async function getMotionJobStatus(jobId: string): Promise<{
  status: string;
  progress?: number;
  result?: any;
}> {
  const response = await apiFetch(`/api/jobs/${jobId}`);
  
  if (!response.ok) {
    throw new Error(`Failed to get job status: ${response.statusText}`);
  }
  
  return response.json();
}
```

- [ ] **Step 2: Update MotionCapturePanel with training submission**

Add to `MotionCapturePanel.tsx`:

```tsx
import { submitMotionForTraining } from '../api/motionCapture';

// Add state
const [motionName, setMotionName] = useState('');
const [isSubmitting, setIsSubmitting] = useState(false);
const [submissionResult, setSubmissionResult] = useState<{
  jobId: string;
  status: string;
} | null>(null);

// Add handler
const handleSubmitForTraining = useCallback(async (bvhContent: string) => {
  if (!motionName.trim()) {
    alert(t('motionCapture.enterMotionName'));
    return;
  }
  
  setIsSubmitting(true);
  try {
    const result = await submitMotionForTraining(bvhContent, motionName);
    setSubmissionResult({
      jobId: result.job_id,
      status: result.status,
    });
  } catch (error) {
    console.error('Failed to submit motion:', error);
  } finally {
    setIsSubmitting(false);
  }
}, [motionName, t]);

// Update onRecordingComplete handler
const handleRecordingComplete = useCallback((result: RecordingResult) => {
  // Show dialog to submit for training
  if (window.confirm(t('motionCapture.submitForTraining'))) {
    handleSubmitForTraining(result.bvh);
  }
}, [handleSubmitForTraining, t]);

// Add UI for motion name input
<div className="motion-name-input">
  <label>{t('motionCapture.motionName')}</label>
  <input
    type="text"
    value={motionName}
    onChange={(e) => setMotionName(e.target.value)}
    placeholder={t('motionCapture.motionNamePlaceholder')}
  />
</div>

{submissionResult && (
  <div className="submission-result">
    {t('motionCapture.jobSubmitted')}: {submissionResult.jobId}
  </div>
)}
```

- [ ] **Step 3: Commit implementation**

```bash
git add web/frontend/src/api/motionCapture.ts
git add web/frontend/src/components/MotionCapturePanel.tsx
git commit -m "feat(frontend): add motion training submission flow"
```

---

## Verification Checkpoints

### Phase 1 Verification

```bash
# Start motion capture service
cd packages/motion_capture
pip install -e ".[dev]"
motion-capture-server &

# Test health endpoint
curl http://localhost:8001/health

# Run tests
pytest tests/ -v
```

### Phase 2 Verification

```bash
# Test retargeting
cd packages/skill_foundry
pip install -e "."
pytest skill_foundry_retarget/tests/ -v
```

### Phase 3 Verification

```bash
# Start frontend dev server
cd web/frontend
npm install
npm run dev

# Open browser, navigate to /pose
# Enable Live Track mode
# Verify camera capture and G1 preview
```

### Phase 4 Verification

```bash
# Run motion training smoke test
cd packages/skill_foundry
pytest skill_foundry_rl/tests/test_amp_discriminator.py -v
pytest skill_foundry_rl/tests/test_reference_motion.py -v

# Full training test (requires GPU)
skill-foundry-train-motion \
  --reference-trajectory data/test_trajectory.json \
  --mjcf-path unitree_mujoco/unitree_robots/g1/scene_29dof.xml \
  --total-timesteps 10000 \
  --output-dir ./test_output
```

### Phase 5 Verification

```bash
# Test motion evaluation
python -c "
from skill_foundry_rl.motion_eval import compute_motion_imitation_score
import numpy as np
policy_traj = np.random.rand(100, 29)
from skill_foundry_rl.reference_motion import ReferenceMotion
ref = ReferenceMotion(np.random.rand(100, 29), 0.02, [])
scores = compute_motion_imitation_score(policy_traj, ref, 0.02)
print(scores)
"
```

### Phase 6 Verification (End-to-End)

```bash
# 1. Start all services
docker-compose up -d  # or manual startup

# 2. Open browser to frontend
# 3. Navigate to Pose Studio
# 4. Enable Live Track
# 5. Start camera
# 6. Record motion
# 7. Submit for training
# 8. Monitor job in Jobs page
# 9. Download skill bundle when complete
```

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
