"""
Train a balance policy for G1 using PPO.

Key fixes vs v1:
- Lower entropy (0.001) to prevent exploration destroying good early policy
- Linear learning rate decay
- Smaller network (128x128) — task is simple
- Gentle push forces initially, eval with same forces
- Lower delta_max (0.15 rad) — only small corrections needed

Usage:
  python train_balance.py [--timesteps 2000000] [--output balance_v2]
"""
import sys
import os
import argparse

try:
    import unitree_sdk2py
except ImportError:
    import types
    mod = types.ModuleType("unitree_sdk2py")
    mod.go2 = types.ModuleType("unitree_sdk2py.go2")
    mod.go2.robot_state = types.ModuleType("unitree_sdk2py.go2.robot_state")
    sys.modules["unitree_sdk2py"] = mod
    sys.modules["unitree_sdk2py.go2"] = mod.go2
    sys.modules["unitree_sdk2py.go2.robot_state"] = mod.go2.robot_state

PLATFORM_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGES_DIR = os.path.join(PLATFORM_DIR, "packages", "skill_foundry")
if PACKAGES_DIR not in sys.path:
    sys.path.insert(0, PACKAGES_DIR)

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv, VecMonitor
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback

from skill_foundry_rl.g1_balance_env import G1BalanceEnv


def make_env(mjcf_path, seed, **kwargs):
    def _init():
        env = G1BalanceEnv(mjcf_path=mjcf_path, **kwargs)
        env.reset(seed=seed)
        return env
    return _init


def linear_schedule(initial_value):
    """Linear decay from initial_value to 0."""
    def func(progress_remaining):
        return progress_remaining * initial_value
    return func


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesteps", type=int, default=2_000_000)
    parser.add_argument("--output", type=str, default="balance_v2")
    parser.add_argument("--n-envs", type=int, default=4)
    parser.add_argument("--eval-freq", type=int, default=25_000)
    args = parser.parse_args()

    mjcf_path = os.path.join(PLATFORM_DIR, "models", "g1_browser", "scene.xml")
    if not os.path.exists(mjcf_path):
        print(f"ERROR: MJCF not found: {mjcf_path}")
        sys.exit(1)

    output_dir = os.path.join(PLATFORM_DIR, args.output)
    os.makedirs(output_dir, exist_ok=True)

    env_kwargs = dict(
        sim_dt=0.002,
        control_dt=0.02,
        delta_max=0.15,            # smaller corrections — task is gentle balance
        min_base_height=0.35,
        max_episode_time=10.0,
        push_force_range=(10.0, 50.0),  # gentler pushes
        push_interval_range=(1.0, 3.0),  # less frequent
        push_duration=0.1,
        waist_perturbation_range=0.2,  # moderate waist variation
    )

    print(f"=== G1 Balance Training v2 ===")
    print(f"  MJCF: {mjcf_path}")
    print(f"  Timesteps: {args.timesteps:,}")
    print(f"  Envs: {args.n_envs}")
    print(f"  delta_max: {env_kwargs['delta_max']}")
    print(f"  push_force: {env_kwargs['push_force_range']}")

    env_fns = [make_env(mjcf_path, seed=i*17, **env_kwargs) for i in range(args.n_envs)]
    vec_env = SubprocVecEnv(env_fns)
    vec_env = VecMonitor(vec_env)

    eval_env = G1BalanceEnv(mjcf_path=mjcf_path, **env_kwargs)

    model = PPO(
        "MlpPolicy",
        vec_env,
        learning_rate=linear_schedule(3e-4),
        n_steps=2048,
        batch_size=128,
        n_epochs=5,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.001,       # LOW entropy — don't destroy good policy
        vf_coef=0.5,
        max_grad_norm=0.5,
        policy_kwargs=dict(
            net_arch=dict(pi=[128, 128], vf=[128, 128]),
        ),
        verbose=1,
        tensorboard_log=os.path.join(output_dir, "tb_logs"),
    )

    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=os.path.join(output_dir, "best"),
        log_path=os.path.join(output_dir, "eval_logs"),
        eval_freq=args.eval_freq // args.n_envs,
        n_eval_episodes=20,
        deterministic=True,
    )

    checkpoint_callback = CheckpointCallback(
        save_freq=50_000 // args.n_envs,
        save_path=os.path.join(output_dir, "checkpoints"),
        name_prefix="bal",
    )

    print("\n--- Training ---")
    model.learn(
        total_timesteps=args.timesteps,
        callback=[eval_callback, checkpoint_callback],
        progress_bar=True,
    )

    final_path = os.path.join(output_dir, "balance_final")
    model.save(final_path)
    print(f"\n✓ Final: {final_path}.zip")

    # Auto-export ONNX
    try:
        import torch
        import torch.nn as nn

        class W(nn.Module):
            def __init__(self, p):
                super().__init__()
                self.fe = p.features_extractor
                self.me = p.mlp_extractor
                self.an = p.action_net
            def forward(self, x):
                f = self.fe(x)
                pi, _ = self.me(f)
                return torch.tanh(self.an(pi))

        w = W(model.policy)
        w.eval()
        dummy = torch.zeros(1, 43)
        onnx_path = os.path.join(output_dir, "balance_policy.onnx")
        torch.onnx.export(w, dummy, onnx_path, opset_version=13,
                          input_names=["obs"], output_names=["action"],
                          dynamic_axes={"obs": {0: "b"}, "action": {0: "b"}})
        print(f"✓ ONNX: {onnx_path} ({os.path.getsize(onnx_path)/1024:.1f} KB)")
    except Exception as e:
        print(f"⚠ ONNX: {e}")

    vec_env.close()
    eval_env.close()
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
