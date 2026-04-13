# Motion Capture Docker Image

Build from repository root:

```bash
docker build -f docker/motion_capture/Dockerfile -t aurosy-motion-capture:0.1 .
```

Run locally:

```bash
docker run --rm -p 8001:8001 aurosy-motion-capture:0.1
```

Optional environment (passed with `-e`):

- `MOTION_CAPTURE_BACKEND=mediapipe` (default). **`vitpose`** is not implemented in the image yet and will fail at runtime if set without a custom build.

Frontend live-track integration expects `WS /ws/capture` to be reachable from the browser:

- local default: `ws://localhost:8001/ws/capture`
- custom endpoint: set `VITE_MOTION_CAPTURE_WS_URL` in frontend repo (`AUROSY_creators_factory/web/frontend`)
- if frontend/backend are behind reverse proxy, ensure WS upgrade rules are configured for the capture route/host.

Health check:

```bash
curl http://localhost:8001/health
```

