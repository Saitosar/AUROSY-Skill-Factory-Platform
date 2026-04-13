# AUROSY Motion Capture Service

Standalone service that receives JPEG frames over WebSocket, runs pose estimation, streams detected landmarks back to the client, and exports a BVH clip for recorded sessions.

## Quickstart

```bash
cd packages/motion_capture
pip install -e ".[dev]"
motion-capture-server
```

## Backend selection (`MOTION_CAPTURE_BACKEND`)

| Value | Behavior |
|-------|----------|
| `mediapipe` (default) | `MediaPipePoseBackend` — CPU-friendly. |
| `vitpose` | **Deferred implementation** — startup raises an actionable `RuntimeError` from `ViTPosePoseBackend.DEFERRED_REASON` until keypoint mapping to 33 MediaPipe landmarks is implemented. Install optional extra `pip install -e ".[vitpose]"` only when contributing that path. |
| Other | Logged warning; falls back to MediaPipe. |

## Endpoints

- `GET /health` - service health status.
- `WS /ws/capture` - real-time capture stream.

## Frontend integration (Phase 3)

- UI repo: `AUROSY_creators_factory/web/frontend`.
- Pose Studio (`/pose`) uses:
  - browser camera capture (`useCameraCapture`)
  - motion WS client (`useMotionCaptureWs`) -> this service
  - backend retarget API `POST /api/pipeline/retarget` -> G1 joint angles
- Default local URL is `ws://<host>:8001/ws/capture`; frontend override: `VITE_MOTION_CAPTURE_WS_URL`.

## WebSocket Message Types

Client to server:
- Binary JPEG frame bytes.
- `{"type":"ping"}`
- `{"type":"start_recording"}`
- `{"type":"stop_recording"}`

Server to client:
- `{"type":"pong"}`
- `{"type":"pose", ...}`
- `{"type":"recording_started"}`
- `{"type":"recording_stopped", "bvh": "...", ...}`

