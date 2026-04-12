#!/usr/bin/env python3
"""Cortex Pipeline training script for Vast.ai.

Trains a policy to track user-provided reference trajectory with safety constraints.
Supports both PyTorch (SB3) and JAX (MuJoCo Playground) backends.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def setup_environment() -> None:
    """Set environment variables for optimal GPU training."""
    os.environ.setdefault("MUJOCO_GL", "egl")
    os.environ.setdefault("XLA_FLAGS", "--xla_gpu_triton_gemm_any=true")
    os.environ.setdefault("JAX_DEFAULT_MATMUL_PRECISION", "highest")


def train_pytorch(
    reference_path: Path,
    mjcf_path: Path,
    output_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Train using PyTorch + Stable-Baselines3."""
    from skill_foundry_rl.ppo_train import run_ppo_train
    
    result = run_ppo_train(
        reference_path=reference_path,
        config=config,
        output_dir=output_dir,
    )
    
    return result


def train_jax(
    reference_path: Path,
    mjcf_path: Path,
    output_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Train using JAX + MuJoCo Playground."""
    try:
        import jax
        from mujoco_playground import locomotion
    except ImportError as e:
        raise RuntimeError(
            "JAX training requires: pip install 'jax[cuda12]' mujoco_playground"
        ) from e
    
    print(f"JAX devices: {jax.devices()}")
    
    env_name = config.get("env_name", "G1JoystickFlatTerrain")
    print(f"Loading environment: {env_name}")
    
    env = locomotion.load(env_name)
    
    total_timesteps = config.get("ppo", {}).get("total_timesteps", 1_000_000)
    
    print(f"Training for {total_timesteps} timesteps...")
    print("Note: Full JAX training loop implementation pending.")
    print("For now, use mujoco_playground's built-in training scripts.")
    
    return {
        "status": "jax_training_stub",
        "env_name": env_name,
        "note": "Use mujoco_playground training scripts for full JAX training",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cortex Pipeline training for Vast.ai",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # PyTorch training (default)
  python train_cortex.py --reference trajectory.json --mjcf scene_29dof.xml

  # JAX training with MuJoCo Playground
  python train_cortex.py --backend jax --reference trajectory.json

  # With custom config
  python train_cortex.py --reference trajectory.json --config train_config.yaml
        """,
    )
    
    parser.add_argument(
        "--reference",
        type=Path,
        required=True,
        help="Path to reference trajectory JSON",
    )
    parser.add_argument(
        "--mjcf",
        type=Path,
        default=None,
        help="Path to G1 MJCF scene (required for PyTorch)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to training config YAML",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/workspace/output"),
        help="Output directory for checkpoints and logs",
    )
    parser.add_argument(
        "--backend",
        choices=["pytorch", "jax"],
        default="pytorch",
        help="Training backend (default: pytorch)",
    )
    parser.add_argument(
        "--timesteps",
        type=int,
        default=100_000,
        help="Total training timesteps (default: 100000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    
    args = parser.parse_args()
    
    setup_environment()
    
    if not args.reference.exists():
        print(f"Error: Reference file not found: {args.reference}", file=sys.stderr)
        return 1
    
    config: dict[str, Any] = {
        "seed": args.seed,
        "ppo": {
            "total_timesteps": args.timesteps,
            "learning_rate": 3e-4,
            "n_steps": 2048,
            "batch_size": 256,
            "n_epochs": 10,
        },
        "env": {
            "sim_dt": 0.005,
            "kp": 150.0,
            "kd": 5.0,
            "delta_max": 0.25,
            "min_base_height": 0.35,
            "enable_collision_check": True,
            "terminate_on_collision": False,
            "reward_weights": {
                "w_track": 1.0,
                "w_alive": 0.02,
                "w_energy": 1.0e-5,
                "w_jerk": 1.0e-6,
                "w_collision": 10.0,
            },
        },
        "early_stop": {
            "eval_freq": 4096,
            "plateau_patience": 10,
            "plateau_min_delta": 0.01,
        },
    }
    
    if args.config and args.config.exists():
        import yaml
        with args.config.open() as f:
            user_config = yaml.safe_load(f)
        if user_config:
            for key, value in user_config.items():
                if isinstance(value, dict) and key in config:
                    config[key].update(value)
                else:
                    config[key] = value
    
    if args.mjcf:
        config["env"]["mjcf_path"] = str(args.mjcf)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_output = args.output / f"run_{timestamp}"
    run_output.mkdir(parents=True, exist_ok=True)
    
    config_path = run_output / "config.json"
    config_path.write_text(json.dumps(config, indent=2))
    
    print("=" * 60)
    print("AUROSY Cortex Pipeline Training")
    print("=" * 60)
    print(f"Backend:    {args.backend}")
    print(f"Reference:  {args.reference}")
    print(f"Output:     {run_output}")
    print(f"Timesteps:  {args.timesteps}")
    print(f"Seed:       {args.seed}")
    print("=" * 60)
    
    try:
        if args.backend == "pytorch":
            if not args.mjcf:
                print("Error: --mjcf required for PyTorch backend", file=sys.stderr)
                return 1
            result = train_pytorch(
                reference_path=args.reference,
                mjcf_path=args.mjcf,
                output_dir=run_output,
                config=config,
            )
        else:
            result = train_jax(
                reference_path=args.reference,
                mjcf_path=args.mjcf,
                output_dir=run_output,
                config=config,
            )
        
        result_path = run_output / "train_result.json"
        result_path.write_text(json.dumps(result, indent=2, default=str))
        
        print("\n" + "=" * 60)
        print("Training complete!")
        print(f"Results saved to: {run_output}")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print(f"\nError during training: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
