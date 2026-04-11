"""Offline behavior cloning on the PPO policy mean (Phase 3.3)."""

from __future__ import annotations

from typing import Any

import numpy as np


def run_bc_pretrain(
    model: Any,
    obs: np.ndarray,
    target_actions: np.ndarray,
    *,
    epochs: int,
    batch_size: int,
    learning_rate: float,
) -> dict[str, Any]:
    """
    Minimize MSE between the Gaussian policy mean and ``target_actions`` (e.g. zeros for ref-only demos).

    Parameters
    ----------
    model
        Stable-Baselines3 ``PPO`` instance (policy on ``model.device``).
    obs
        Shape (N, obs_dim), float32/float64.
    target_actions
        Shape (N, 29), same scale as policy output in [-1, 1].
    """
    import torch
    from torch.nn import functional as F

    if epochs <= 0:
        return {"bc_epochs": 0, "bc_batches": 0, "bc_final_loss": None}

    policy = model.policy
    device = model.device
    n = int(obs.shape[0])
    if int(target_actions.shape[0]) != n:
        raise ValueError("obs and target_actions must have same length")

    opt = torch.optim.Adam(policy.parameters(), lr=float(learning_rate))
    obs_t_full = torch.as_tensor(np.asarray(obs), dtype=torch.float32, device=device)
    tgt_t = torch.as_tensor(np.asarray(target_actions), dtype=torch.float32, device=device)

    final_loss: float | None = None
    batches = 0
    for _epoch in range(int(epochs)):
        perm = torch.randperm(n, device=device)
        for start in range(0, n, int(batch_size)):
            batches += 1
            idx = perm[start : start + int(batch_size)]
            batch_obs = obs_t_full[idx]
            batch_tgt = tgt_t[idx]
            dist = policy.get_distribution(batch_obs)
            pred = dist.mode()
            loss = F.mse_loss(pred, batch_tgt)
            opt.zero_grad()
            loss.backward()
            opt.step()
            final_loss = float(loss.item())

    return {
        "bc_epochs": int(epochs),
        "bc_batches": batches,
        "bc_final_loss": final_loss,
    }
