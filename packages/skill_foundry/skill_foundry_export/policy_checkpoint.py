"""Extract policy weights from a Stable-Baselines3 PPO zip checkpoint."""

from __future__ import annotations

from pathlib import Path

import torch


def export_policy_state_dict(checkpoint_zip: Path, out_pt: Path) -> None:
    """Load PPO from ``checkpoint_zip`` and save ``policy.state_dict()`` to ``out_pt``."""
    from stable_baselines3 import PPO

    model = PPO.load(str(checkpoint_zip))
    sd = model.policy.state_dict()
    torch.save({"policy_state_dict": sd, "format": "stable_baselines3_actor_critic_policy"}, out_pt)
