"""Runtime observation vector matches G1TrackingEnv."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from skill_foundry_rl.g1_tracking_env import G1TrackingEnv, G1TrackingEnvConfig
from skill_foundry_runtime.observation import build_tracking_observation
from skill_foundry_sim.reference_loader import load_reference_trajectory_json

_REPO = Path(__file__).resolve().parents[4]
_MJCF = _REPO / "unitree_mujoco" / "unitree_robots" / "g1" / "scene_29dof.xml"
_REF = _REPO / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"


@pytest.mark.skipif(not _MJCF.is_file(), reason="unitree_mujoco scene not present")
@pytest.mark.skipif(not _REF.is_file(), reason="golden reference not present")
def test_obs_matches_env_after_reset() -> None:
    pytest.importorskip("gymnasium")
    ref = load_reference_trajectory_json(_REF)
    cfg = G1TrackingEnvConfig(mjcf_path=str(_MJCF), sim_dt=0.005, min_base_height=0.2)
    env = G1TrackingEnv(ref, cfg)
    obs_env, _ = env.reset(seed=11)

    motor_q = env._data.sensordata[: env.nu].copy()
    motor_dq = env._data.sensordata[env.nu : 2 * env.nu].copy()
    obs_rt = build_tracking_observation(
        ref,
        list(ref["joint_order"]),
        0.0,
        motor_q,
        motor_dq,
        include_imu=False,
    )
    np.testing.assert_allclose(obs_rt, obs_env, rtol=0, atol=1e-9)


@pytest.mark.skipif(not _MJCF.is_file(), reason="unitree_mujoco scene not present")
@pytest.mark.skipif(not _REF.is_file(), reason="golden reference not present")
def test_obs_matches_env_after_steps() -> None:
    pytest.importorskip("gymnasium")
    ref = load_reference_trajectory_json(_REF)
    cfg = G1TrackingEnvConfig(mjcf_path=str(_MJCF), sim_dt=0.005, min_base_height=0.2)
    env = G1TrackingEnv(ref, cfg)
    env.reset(seed=3)
    a = np.linspace(-0.1, 0.1, 29)
    for _ in range(10):
        _o, _r, _term, _trunc, _info = env.step(a)

    motor_q = env._data.sensordata[: env.nu].copy()
    motor_dq = env._data.sensordata[env.nu : 2 * env.nu].copy()
    t = float(env._episode_time)
    obs_env = env._get_obs()
    obs_rt = build_tracking_observation(
        ref,
        list(ref["joint_order"]),
        t,
        motor_q,
        motor_dq,
        include_imu=False,
    )
    np.testing.assert_allclose(obs_rt, obs_env, rtol=0, atol=1e-9)
