from __future__ import annotations

import torch

from skill_foundry_rl.amp_discriminator import AMPDiscriminator


def test_amp_discriminator_forward_and_reward_shapes() -> None:
    disc = AMPDiscriminator(state_dim=87, hidden_dim=64, num_layers=2)
    s = torch.randn(16, 87)
    sn = torch.randn(16, 87)
    logits = disc(s, sn)
    rew = disc.amp_reward(s, sn)
    assert logits.shape == (16, 1)
    assert rew.shape == (16,)


def test_amp_discriminator_loss_metrics_keys() -> None:
    disc = AMPDiscriminator(state_dim=87, hidden_dim=64, num_layers=2)
    e_s = torch.randn(12, 87)
    e_n = torch.randn(12, 87)
    p_s = torch.randn(12, 87)
    p_n = torch.randn(12, 87)
    loss, metrics = disc.loss(e_s, e_n, p_s, p_n)
    assert float(loss.item()) >= 0.0
    assert "disc_total_loss" in metrics
    assert "disc_expert_score" in metrics
    assert "disc_policy_score" in metrics
