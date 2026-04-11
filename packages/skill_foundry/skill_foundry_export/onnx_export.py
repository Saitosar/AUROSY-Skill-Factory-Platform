"""Export SB3 PPO policy mean action as ONNX (deterministic inference)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn as nn


class _PolicyMeanWrapper(nn.Module):
    """Maps observation vector to Gaussian mean actions (before sampling), MlpPolicy."""

    def __init__(self, policy: Any) -> None:
        super().__init__()
        self.features_extractor = policy.features_extractor
        self.mlp_extractor = policy.mlp_extractor
        self.action_net = policy.action_net

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        features = self.features_extractor(obs)
        latent_pi, _ = self.mlp_extractor(features)
        return self.action_net(latent_pi)


def export_ppo_policy_onnx(
    checkpoint_zip: Path,
    out_onnx: Path,
    *,
    obs_dim: int,
    opset: int = 17,
) -> dict[str, Any]:
    """
    Trace ``action_net(mlp(extract(obs)))`` and export to ONNX.

    Returns metadata for manifest (input/output names, shapes).
    """
    try:
        import onnx  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "ONNX export requires the 'onnx' package. Install with: pip install onnx"
        ) from exc

    from stable_baselines3 import PPO

    model = PPO.load(str(checkpoint_zip))
    wrapper = _PolicyMeanWrapper(model.policy)
    wrapper.eval()

    dummy = torch.zeros(1, obs_dim, dtype=torch.float32)
    out_path = Path(out_onnx)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    input_name = "obs"
    output_name = "action_mean"
    export_kw: dict[str, Any] = {
        "input_names": [input_name],
        "output_names": [output_name],
        "opset_version": opset,
    }
    try:
        import inspect

        if "dynamo" in inspect.signature(torch.onnx.export).parameters:
            export_kw["dynamo"] = False
    except (TypeError, ValueError):
        pass
    torch.onnx.export(wrapper, dummy, str(out_path), **export_kw)

    action_dim = int(model.action_space.shape[0])
    return {
        "input_name": input_name,
        "output_name": output_name,
        "obs_dim": obs_dim,
        "action_dim": action_dim,
    }
