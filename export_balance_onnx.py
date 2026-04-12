"""
Export trained balance policy to ONNX for browser inference.

Usage:
  python export_balance_onnx.py [--model balance_policy/best/best_model.zip] [--output balance_policy.onnx]
"""
import sys
import os
import argparse

# Mock unitree SDK
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
import torch
import torch.nn as nn
from stable_baselines3 import PPO


class PolicyWrapper(nn.Module):
    """Wraps SB3 policy's MLP to output deterministic action (mean only)."""

    def __init__(self, policy):
        super().__init__()
        self.features_extractor = policy.features_extractor
        self.mlp_extractor = policy.mlp_extractor
        self.action_net = policy.action_net

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        features = self.features_extractor(obs)
        pi_latent, _ = self.mlp_extractor(features)
        return torch.tanh(self.action_net(pi_latent))  # clip to [-1, 1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="balance_policy/best/best_model.zip")
    parser.add_argument("--output", type=str, default="balance_policy/balance_policy.onnx")
    args = parser.parse_args()

    model_path = os.path.join(PLATFORM_DIR, args.model)
    if not os.path.exists(model_path):
        # Try without .zip
        alt = model_path.replace(".zip", "")
        if os.path.exists(alt + ".zip"):
            model_path = alt + ".zip"
        else:
            print(f"ERROR: Model not found: {model_path}")
            sys.exit(1)

    print(f"Loading model: {model_path}")
    model = PPO.load(model_path)

    wrapper = PolicyWrapper(model.policy)
    wrapper.eval()

    # Observation dim = 43
    dummy_input = torch.zeros(1, 43, dtype=torch.float32)

    # Test forward pass
    with torch.no_grad():
        test_output = wrapper(dummy_input)
        print(f"Test output shape: {test_output.shape}")  # Should be (1, 12)
        print(f"Test output: {test_output.numpy().flatten()}")

    # Export to ONNX
    output_path = os.path.join(PLATFORM_DIR, args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    torch.onnx.export(
        wrapper,
        dummy_input,
        output_path,
        opset_version=13,
        input_names=["obs"],
        output_names=["action"],
        dynamic_axes={
            "obs": {0: "batch"},
            "action": {0: "batch"},
        },
    )

    file_size = os.path.getsize(output_path)
    print(f"\n✓ ONNX exported: {output_path} ({file_size / 1024:.1f} KB)")
    print(f"  Input: obs [batch, 43] (float32)")
    print(f"  Output: action [batch, 12] (float32, range [-1, 1])")
    print(f"  Action = leg joint target residuals × delta_max (0.3 rad)")


if __name__ == "__main__":
    main()
