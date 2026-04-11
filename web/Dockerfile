FROM python:3.11-slim

WORKDIR /opt/app

# Install Python dependencies
COPY web/backend/requirements.txt ./web/backend/requirements.txt
RUN pip install --no-cache-dir -r ./web/backend/requirements.txt

# Copy FastAPI app (maintain path structure: web/backend/app/config.py uses parents[3] as repo root)
COPY web/backend/app ./web/backend/app

# Copy unitree_sdk2_python (needed for CLI subprocess invocation and path resolution)
COPY unitree_sdk2_python ./unitree_sdk2_python

# Persistent data directory (SQLite + job workspaces)
RUN mkdir -p web/backend/data/platform

ENV G1_DDS_JOINT_BRIDGE=false
ENV G1_USE_DDS_TELEMETRY=false
ENV G1_PLATFORM_WORKER_ENABLED=1
ENV G1_DDS_INTERFACE=lo
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/app/web/backend
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
