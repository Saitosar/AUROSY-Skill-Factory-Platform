# Vast.ai Training for AUROSY Cortex Pipeline

GPU-accelerated training for Unitree G1 motion policies on [Vast.ai](https://vast.ai).

## Quick Start

### 1. Create Vast.ai Instance

```bash
# Recommended: RTX 4090, CUDA 12.x, 100GB disk
vastai create instance <OFFER_ID> \
  --image pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel \
  --env '-e MUJOCO_GL="egl" -e XLA_FLAGS="--xla_gpu_triton_gemm_any=true"' \
  --disk 100 \
  --jupyter --ssh --direct
```

### 2. SSH and Setup

```bash
ssh -p <PORT> root@<IP>

# Run setup script
cd /workspace
wget https://raw.githubusercontent.com/YOUR_ORG/AUROSY_creators_factory_platform/main/vast_training/setup_vast.sh
bash setup_vast.sh --pytorch  # or --jax for JAX backend
```

### 3. Upload Data

```bash
# From local machine
scp -P <PORT> reference_trajectory.json root@<IP>:/workspace/data/
scp -P <PORT> scene_29dof.xml root@<IP>:/workspace/data/
```

### 4. Train

```bash
# Start training in tmux (persists if SSH disconnects)
tmux new -s train

python train_cortex.py \
  --reference /workspace/data/reference_trajectory.json \
  --mjcf /workspace/data/scene_29dof.xml \
  --output /workspace/output \
  --timesteps 100000

# Detach: Ctrl+B, then D
# Reattach: tmux attach -t train
```

### 5. Monitor

```bash
# TensorBoard (in separate terminal)
tensorboard --logdir /workspace/output --port 6006 --bind_all
```

Access via: `http://<INSTANCE_IP>:6006`

### 6. Download Results

```bash
# From local machine
scp -P <PORT> -r root@<IP>:/workspace/output/run_* ./results/
```

## Training Backends

### PyTorch + Stable-Baselines3 (Default)

- Uses existing `G1TrackingEnv` with collision detection
- PPO algorithm with configurable hyperparameters
- Exports `.zip` checkpoint compatible with `skill_foundry_runtime`

```bash
python train_cortex.py --backend pytorch --reference traj.json --mjcf scene.xml
```

### JAX + MuJoCo Playground

- GPU-accelerated physics simulation
- ~100x faster than CPU-based training
- Requires `mujoco_playground` installation

```bash
python train_cortex.py --backend jax --reference traj.json
```

## Configuration

Create `train_config.yaml`:

```yaml
seed: 42

ppo:
  total_timesteps: 500000
  learning_rate: 3e-4
  n_steps: 2048
  batch_size: 256
  n_epochs: 10
  gamma: 0.99

env:
  sim_dt: 0.005
  kp: 150.0
  kd: 5.0
  delta_max: 0.25
  min_base_height: 0.35
  enable_collision_check: true
  terminate_on_collision: false
  reward_weights:
    w_track: 1.0
    w_alive: 0.02
    w_energy: 1.0e-5
    w_jerk: 1.0e-6
    w_collision: 10.0

early_stop:
  eval_freq: 4096
  plateau_patience: 10
  plateau_min_delta: 0.01
```

Run with config:

```bash
python train_cortex.py --reference traj.json --mjcf scene.xml --config train_config.yaml
```

## Cost Estimation

| Instance | Training Time | Cost |
|----------|--------------|------|
| RTX 4090 (PyTorch, 100k steps) | ~30-60 min | ~$0.40 |
| RTX 4090 (JAX, 1M steps) | ~30-60 min | ~$0.40 |
| RTX 3090 (PyTorch, 100k steps) | ~60-90 min | ~$0.30 |

## Troubleshooting

### CUDA out of memory

Reduce batch size in config:

```yaml
ppo:
  batch_size: 128  # or 64
```

### MuJoCo rendering issues

Ensure EGL is set:

```bash
export MUJOCO_GL=egl
```

### SSH connection drops

Use `tmux` or `screen` to persist sessions:

```bash
tmux new -s train
# ... run training ...
# Ctrl+B, D to detach
```

## Files

- `setup_vast.sh` — Environment setup script
- `train_cortex.py` — Main training script
- `README.md` — This file
