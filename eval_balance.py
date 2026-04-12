"""
Evaluate trained balance policy in native MuJoCo.
Shows detailed stats: survival rate, average height, max tilt, etc.

Usage:
  python eval_balance.py [--model balance_policy/best/best_model.zip] [--episodes 20]
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
sys.path.insert(0, os.path.join(PLATFORM_DIR, "packages", "skill_foundry"))

import numpy as np
from stable_baselines3 import PPO
from skill_foundry_rl.g1_balance_env import G1BalanceEnv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="balance_policy/best/best_model.zip")
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--push-force", type=float, nargs=2, default=[30, 100])
    args = parser.parse_args()

    model_path = os.path.join(PLATFORM_DIR, args.model)
    print(f"Loading: {model_path}")
    model = PPO.load(model_path)

    mjcf = os.path.join(PLATFORM_DIR, "models", "g1_browser", "scene.xml")
    env = G1BalanceEnv(
        mjcf_path=mjcf,
        push_force_range=tuple(args.push_force),
    )

    survived = 0
    rewards = []
    heights = []
    times = []

    for ep in range(args.episodes):
        obs, _ = env.reset(seed=ep)
        total_r = 0
        min_h = 1.0
        for step in range(500):
            action, _ = model.predict(obs, deterministic=True)
            obs, r, term, trunc, info = env.step(action)
            total_r += r
            min_h = min(min_h, info["base_height"])
            if term or trunc:
                break

        ep_time = info["time"]
        ok = not info["fallen"]
        survived += int(ok)
        rewards.append(total_r)
        heights.append(min_h)
        times.append(ep_time)

        status = "✓" if ok else "✗"
        print(f"  Ep {ep+1:2d}: {status}  time={ep_time:.1f}s  reward={total_r:.0f}  min_h={min_h:.3f}")

    print(f"\n{'='*40}")
    print(f"Survival: {survived}/{args.episodes} ({100*survived/args.episodes:.0f}%)")
    print(f"Mean reward: {np.mean(rewards):.0f} ± {np.std(rewards):.0f}")
    print(f"Mean time: {np.mean(times):.1f}s")
    print(f"Mean min height: {np.mean(heights):.3f}")
    print(f"Push force: {args.push_force[0]}-{args.push_force[1]} N")

    env.close()


if __name__ == "__main__":
    main()
