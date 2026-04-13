"""Motion Capture WebSocket server."""

from __future__ import annotations

import json
import logging
from typing import Dict, Optional

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .bvh_export import BVHExporter, RecordingSession
from .balance_inference import load_balance_inferencer_from_env
from .pose_backend import PoseBackend, create_pose_backend_from_env

logger = logging.getLogger(__name__)


class CaptureSession:
    def __init__(self, backend: PoseBackend):
        self.backend = backend
        self.recording = RecordingSession(fps=30.0)
        self.is_recording = False
        self.exporter = BVHExporter()
        self.retargeter = None
        self.joint_order: list[str] = []
        self.balance_inferencer = load_balance_inferencer_from_env()
        try:
            from skill_foundry_retarget import Retargeter, load_joint_map

            self.retargeter = Retargeter(joint_map=load_joint_map(), clip_to_limits=True)
            self.joint_order = list(self.retargeter.joint_order)
        except Exception:
            self.retargeter = None
            self.joint_order = []

    def process_frame(self, frame_data: bytes) -> Optional[Dict]:
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

        joint_angles_rad: list[float] | None = None
        balance_timing_ms = 0.0
        if self.retargeter is not None:
            try:
                retarget = self.retargeter.compute(result.landmarks)
                joints = retarget.joint_angles_rad
                if self.balance_inferencer is not None:
                    balanced = self.balance_inferencer.apply(joints)
                    joints = balanced.joint_angles_rad
                    balance_timing_ms = balanced.elapsed_ms
                joint_angles_rad = joints.tolist()
            except Exception:
                joint_angles_rad = None

        payload: Dict = {
            "type": "pose",
            "landmarks": result.landmarks.tolist(),
            "confidence": result.confidence,
            "timestamp_ms": result.timestamp_ms,
        }
        if joint_angles_rad is not None:
            payload["joint_order"] = self.joint_order
            payload["joint_angles_rad"] = joint_angles_rad
            if balance_timing_ms > 0:
                payload["balance_timing_ms"] = balance_timing_ms
        return payload

    def start_recording(self) -> None:
        self.recording.clear()
        self.is_recording = True

    def stop_recording(self) -> Dict:
        self.is_recording = False
        bvh = self.exporter.export(self.recording)
        landmarks_frames = [frame.tolist() for frame, _ in self.recording.frames]
        return {
            "bvh": bvh,
            "duration_sec": self.recording.duration_sec,
            "frame_count": self.recording.frame_count,
            "landmarks_frames": landmarks_frames,
        }


def create_app() -> FastAPI:
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
        backend = create_pose_backend_from_env()
        session = CaptureSession(backend)

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                if "text" in message and message["text"] is not None:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")

                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif msg_type == "start_recording":
                        session.start_recording()
                        await websocket.send_json({"type": "recording_started"})
                    elif msg_type == "stop_recording":
                        record_result = session.stop_recording()
                        await websocket.send_json(
                            {
                                "type": "recording_stopped",
                                "bvh": record_result["bvh"],
                                "duration_sec": record_result["duration_sec"],
                                "frame_count": record_result["frame_count"],
                                "landmarks_frames": record_result["landmarks_frames"],
                            }
                        )

                elif "bytes" in message and message["bytes"] is not None:
                    result = session.process_frame(message["bytes"])
                    if result:
                        await websocket.send_json(result)

        except WebSocketDisconnect:
            logger.info("Client disconnected")
        finally:
            backend.close()

    return app


def main() -> None:
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()

