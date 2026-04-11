# Skill Foundry RL worker — Phase 3.1
# Stack: PyTorch + CUDA (base image), Python from base, MuJoCo via unitree_sdk2py[rl].
# Reproducibility: pin this tag when upgrading; record in docs/skill_foundry/08_phase3_rl_worker_docker.md
#
# Build from repository root:
#   docker build -f docker/skill_foundry_rl/Dockerfile -t skill-foundry-rl:3.1 .
#
# On Apple Silicon, the PyTorch image is often linux/amd64; Docker may emulate.
# To pin: docker build --platform linux/amd64 -f docker/skill_foundry_rl/Dockerfile -t skill-foundry-rl:3.1 .

FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

LABEL org.opencontainers.image.title="Skill Foundry RL worker"
LABEL org.opencontainers.image.description="Skill Foundry RL worker: smoke (3.1) and PPO train (3.2); see docs/skill_foundry/08_phase3_rl_worker_docker.md and 09_phase3_env_rewards.md"

ENV DEBIAN_FRONTEND=noninteractive \
    MUJOCO_GL=egl \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# unitree_sdk2py depends on cyclonedds (pip), which needs the Cyclone DDS C library installed first.
ENV CYCLONEDDS_HOME=/usr/local
ENV CMAKE_PREFIX_PATH=/usr/local
RUN git clone --depth 1 --branch 0.10.2 https://github.com/eclipse-cyclonedds/cyclonedds.git /tmp/cyclonedds \
    && cmake -S /tmp/cyclonedds -B /tmp/cyclonedds/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="${CYCLONEDDS_HOME}" \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_TESTING=OFF \
    && cmake --build /tmp/cyclonedds/build --target install -j"$(nproc)" \
    && rm -rf /tmp/cyclonedds

WORKDIR /opt/skill_foundry

COPY unitree_sdk2_python /opt/skill_foundry/unitree_sdk2_python

RUN pip install --no-cache-dir -e "/opt/skill_foundry/unitree_sdk2_python[rl]"

ENTRYPOINT ["skill-foundry-train"]
CMD ["--help"]
