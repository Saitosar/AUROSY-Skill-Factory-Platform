"""AMP discriminator module and loss helpers."""

from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F


class AMPDiscriminator(nn.Module):
    """Binary discriminator over state transitions (expert vs policy)."""

    def __init__(self, state_dim: int, hidden_dim: int = 256, num_layers: int = 2):
        super().__init__()
        if state_dim < 1:
            raise ValueError("state_dim must be positive")
        if num_layers < 1:
            raise ValueError("num_layers must be >= 1")

        in_dim = state_dim * 2
        layers: list[nn.Module] = [nn.Linear(in_dim, hidden_dim), nn.ReLU()]
        for _ in range(num_layers - 1):
            layers.extend([nn.Linear(hidden_dim, hidden_dim), nn.ReLU()])
        layers.append(nn.Linear(hidden_dim, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, states: torch.Tensor, next_states: torch.Tensor) -> torch.Tensor:
        if states.shape != next_states.shape:
            raise ValueError("states and next_states must have same shape")
        x = torch.cat([states, next_states], dim=-1)
        return self.net(x)

    def amp_reward(self, states: torch.Tensor, next_states: torch.Tensor) -> torch.Tensor:
        """AMP-style reward: -log(1 - D(s,s'))."""
        with torch.no_grad():
            logits = self.forward(states, next_states)
            prob = torch.sigmoid(logits)
            reward = -torch.log(torch.clamp(1.0 - prob, min=1e-8))
            return reward.squeeze(-1)

    def loss(
        self,
        expert_states: torch.Tensor,
        expert_next_states: torch.Tensor,
        policy_states: torch.Tensor,
        policy_next_states: torch.Tensor,
    ) -> tuple[torch.Tensor, dict[str, float]]:
        expert_logits = self.forward(expert_states, expert_next_states)
        policy_logits = self.forward(policy_states, policy_next_states)
        expert_loss = F.binary_cross_entropy_with_logits(expert_logits, torch.ones_like(expert_logits))
        policy_loss = F.binary_cross_entropy_with_logits(policy_logits, torch.zeros_like(policy_logits))
        total = expert_loss + policy_loss
        metrics: dict[str, Any] = {
            "disc_total_loss": float(total.item()),
            "disc_expert_loss": float(expert_loss.item()),
            "disc_policy_loss": float(policy_loss.item()),
            "disc_expert_score": float(torch.sigmoid(expert_logits).mean().item()),
            "disc_policy_score": float(torch.sigmoid(policy_logits).mean().item()),
        }
        return total, metrics
