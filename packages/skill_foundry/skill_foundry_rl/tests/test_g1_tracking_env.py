"""G1TrackingEnv shape and determinism."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from skill_foundry_rl.g1_tracking_env import G1TrackingEnv, G1TrackingEnvConfig
from skill_foundry_rl.obs_schema import RL_OBS_DIM_BASE, RL_OBS_SCHEMA_REF, rl_obs_dim
from skill_foundry_sim.reference_loader import load_reference_trajectory_json

_REPO = Path(__file__).resolve().parents[4]
_MJCF = _REPO / "unitree_mujoco" / "unitree_robots" / "g1" / "scene_29dof.xml"
_REF = _REPO / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"


@pytest.mark.skipif(not _MJCF.is_file(), reason="unitree_mujoco scene not present")
@pytest.mark.skipif(not _REF.is_file(), reason="golden reference not present")
def test_obs_dim_and_schema() -> None:
    pytest.importorskip("gymnasium")
    ref = load_reference_trajectory_json(_REF)
    cfg = G1TrackingEnvConfig(mjcf_path=str(_MJCF), sim_dt=0.005, min_base_height=0.2)
    env = G1TrackingEnv(ref, cfg)
    assert env.observation_space.shape[0] == RL_OBS_DIM_BASE == rl_obs_dim(include_imu=False)
    o, _ = env.reset(seed=7)
    assert o.shape == (RL_OBS_DIM_BASE,)
    assert RL_OBS_SCHEMA_REF == "skill_foundry_rl_tracking_v1"


@pytest.mark.skipif(not _MJCF.is_file(), reason="unitree_mujoco scene not present")
@pytest.mark.skipif(not _REF.is_file(), reason="golden reference not present")
def test_reset_step_deterministic() -> None:
    pytest.importorskip("gymnasium")
    ref = load_reference_trajectory_json(_REF)
    cfg = G1TrackingEnvConfig(mjcf_path=str(_MJCF), sim_dt=0.005, min_base_height=0.2)

    def rollout(seed: int) -> tuple[np.ndarray, float]:
        env = G1TrackingEnv(ref, cfg)
        obs, _ = env.reset(seed=seed)
        r_total = 0.0
        a = np.zeros(29, dtype=np.float64)
        for _ in range(5):
            obs, r, _, _, _ = env.step(a)
            r_total += r
        return obs, r_total

    o1, rt1 = rollout(42)
    o2, rt2 = rollout(42)
    np.testing.assert_allclose(o1, o2, rtol=0, atol=1e-9)
    assert rt1 == rt2
