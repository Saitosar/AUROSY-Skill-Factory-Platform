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
from .pose_backend import PoseBackend, create_pose_backend_from_env

logger = logging.getLogger(__name__)


class CaptureSession:
    def __init__(self, backend: PoseBackend):
        self.backend = backend
        self.recording = RecordingSession(fps=30.0)
        self.is_recording = False
        self.exporter = BVHExporter()

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
                        bvh_content = session.stop_recording()
                        await websocket.send_json(
                            {
                                "type": "recording_stopped",
                                "bvh": bvh_content,
                                "duration_sec": session.recording.duration_sec,
                                "frame_count": session.recording.frame_count,
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

