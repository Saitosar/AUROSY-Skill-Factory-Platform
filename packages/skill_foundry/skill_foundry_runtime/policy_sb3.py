"""Load SB3 PPO checkpoint from skill package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def load_ppo_policy(ckpt_path: Path | str) -> Any:
    from stable_baselines3 import PPO

    return PPO.load(str(ckpt_path))


def predict_action(
    model: Any,
    obs: np.ndarray,
    *,
    deterministic: bool = True,
) -> np.ndarray:
    action, _ = model.predict(obs, deterministic=deterministic)
    return np.asarray(action, dtype=np.float64).ravel()
