FROM python:3.11-slim

LABEL org.opencontainers.image.title="AUROSY Motion Capture Service"
LABEL org.opencontainers.image.description="WebSocket motion capture service with MediaPipe pose backend and BVH export."

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY packages/motion_capture /app/packages/motion_capture
RUN pip install --no-cache-dir /app/packages/motion_capture

EXPOSE 8001

ENTRYPOINT ["motion-capture-server"]

