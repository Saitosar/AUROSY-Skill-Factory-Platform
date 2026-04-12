#!/bin/bash
# Vast.ai environment setup for AUROSY Cortex Pipeline
# Usage: bash setup_vast.sh [--jax|--pytorch]
#
# Recommended instance: RTX 4090, CUDA 12.x, 100GB disk
# Image: pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel or nvcr.io/nvidia/jax:24.04-py3

set -e

MODE="${1:-pytorch}"

echo "=========================================="
echo "AUROSY Cortex Pipeline - Vast.ai Setup"
echo "Mode: $MODE"
echo "=========================================="

# Environment variables for optimal performance
export MUJOCO_GL=egl
export XLA_FLAGS="--xla_gpu_triton_gemm_any=true"
export JAX_DEFAULT_MATMUL_PRECISION=highest
export PYTHONUNBUFFERED=1

# System dependencies
echo "[1/6] Installing system dependencies..."
apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    wget \
    libeigen3-dev \
    libgl1-mesa-glx \
    libosmesa6-dev \
    libglfw3 \
    patchelf \
    && rm -rf /var/lib/apt/lists/*

# Python packages based on mode
echo "[2/6] Installing Python packages ($MODE mode)..."
pip install --upgrade pip

if [ "$MODE" = "jax" ]; then
    echo "Installing JAX with CUDA support..."
    pip install --no-cache-dir \
        "jax[cuda12]" \
        mujoco>=3.2.0 \
        mujoco_playground \
        gymnasium \
        tensorboard \
        wandb \
        pyyaml
else
    echo "Installing PyTorch stack..."
    pip install --no-cache-dir \
        torch>=2.0 \
        mujoco>=3.2.0 \
        gymnasium>=0.29.0 \
        stable-baselines3>=2.3.0 \
        tensorboard \
        wandb \
        pyyaml
fi

# Pinocchio for NMR (IK correction)
echo "[3/6] Installing Pinocchio..."
pip install --no-cache-dir pin

# Clone or update repository
echo "[4/6] Setting up repository..."
REPO_DIR="/workspace/aurosy_platform"
REPO_URL="${AUROSY_REPO_URL:-https://github.com/YOUR_ORG/AUROSY_creators_factory_platform.git}"

if [ -d "$REPO_DIR" ]; then
    echo "Repository exists, pulling latest..."
    cd "$REPO_DIR"
    git pull || true
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$REPO_DIR" || {
        echo "Warning: Could not clone repo. Creating local workspace..."
        mkdir -p "$REPO_DIR"
    }
fi

# Install skill_foundry package
echo "[5/6] Installing skill_foundry..."
if [ -d "$REPO_DIR/packages/skill_foundry" ]; then
    cd "$REPO_DIR/packages/skill_foundry"
    pip install -e ".[rl,validation]" || echo "Warning: skill_foundry install failed"
fi

# Verify installation
echo "[6/6] Verifying installation..."
echo ""
echo "Python packages:"
python -c "import mujoco; print(f'  MuJoCo: {mujoco.__version__}')"

if [ "$MODE" = "jax" ]; then
    python -c "import jax; print(f'  JAX devices: {jax.devices()}')"
    python -c "from mujoco_playground import locomotion; print('  MuJoCo Playground: OK')" || echo "  MuJoCo Playground: Not available"
else
    python -c "import torch; print(f'  PyTorch: {torch.__version__}')"
    python -c "print(f'  CUDA available: {torch.cuda.is_available()}')"
    python -c "from stable_baselines3 import PPO; print('  Stable-Baselines3: OK')"
fi

python -c "import pinocchio; print('  Pinocchio: OK')" || echo "  Pinocchio: Not available"

echo ""
echo "=========================================="
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Upload your reference trajectory JSON"
echo "  2. Run training:"
if [ "$MODE" = "jax" ]; then
    echo "     python train_cortex_mjx.py --reference /workspace/data/reference.json"
else
    echo "     skill-foundry-train --reference /workspace/data/reference.json --config train_config.yaml"
fi
echo ""
echo "  3. Monitor with TensorBoard:"
echo "     tensorboard --logdir /workspace/logs --port 6006"
echo ""
echo "  4. Download results from /workspace/output/"
echo "=========================================="
