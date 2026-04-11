"""Demonstration → RL obs alignment vs G1TrackingEnv."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from skill_foundry_rl.demo_rl_align import (
    build_bc_dataset_arrays,
    demo_step_time_s,
    rl_obs_from_demo_step,
)
from skill_foundry_rl.g1_tracking_env import G1TrackingEnv, G1TrackingEnvConfig
from skill_foundry_sim.demonstration_dataset import build_demonstration_dataset
from skill_foundry_sim.headless_playback import PlaybackConfig, run_headless_playback


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


def _mjcf() -> Path:
    p = _repo() / "unitree_mujoco" / "unitree_robots" / "g1" / "scene_29dof.xml"
    if not p.is_file():
        pytest.skip(f"MJCF not found: {p}")
    return p


def _minimal_reference_29dof() -> dict:
    order = [str(i) for i in range(29)]
    positions = [[0.01 * (i % 5) for i in range(29)] for _ in range(8)]
    return {
        "schema_version": "1.0.0",
        "robot_model": "g1_29dof",
        "units": {"angle": "radians", "time": "seconds"},
        "frequency_hz": 50.0,
        "root_model": "root_not_in_reference",
        "joint_order": order,
        "joint_positions": positions,
    }


def test_demo_step_time_matches_sim_dt() -> None:
    assert demo_step_time_s(0, 200.0) == pytest.approx(0.005)
    assert demo_step_time_s(1, 200.0) == pytest.approx(0.01)


@pytest.mark.skipif(not _mjcf().is_file(), reason="MJCF not present")
def test_aligned_obs_matches_env_after_steps() -> None:
    pytest.importorskip("mujoco")
    pytest.importorskip("gymnasium")
    ref = _minimal_reference_29dof()
    cfg_pb = PlaybackConfig(
        mjcf_path=str(_mjcf()),
        sim_dt=0.005,
        mode="dynamic",
        kp=120.0,
        kd=4.0,
        seed=21,
        max_steps=15,
    )
    log = run_headless_playback(ref, cfg_pb)
    demo = build_demonstration_dataset(
        log,
        robot_model="g1_29dof",
        sim_dt=cfg_pb.sim_dt,
        seed=cfg_pb.seed,
        simulator_commit="test",
        include_ref=True,
    )

    hz = float(demo["sampling_hz"])
    env_cfg = G1TrackingEnvConfig(
        mjcf_path=str(_mjcf()),
        sim_dt=cfg_pb.sim_dt,
        kp=cfg_pb.kp,
        kd=cfg_pb.kd,
        min_base_height=0.2,
    )
    env = G1TrackingEnv(ref, env_cfg)
    obs_env, _ = env.reset(seed=21)
    a0 = np.zeros(29, dtype=np.float64)

    for k, step in enumerate(demo["episodes"][0]["steps"]):
        o58 = np.asarray(step["obs"], dtype=np.float64)
        t = demo_step_time_s(k, hz)
        o_align = rl_obs_from_demo_step(o58, ref, t)
        obs_env, _, _, _, _ = env.step(a0)
        np.testing.assert_allclose(o_align, obs_env, rtol=0, atol=1e-5)


@pytest.mark.skipif(not _mjcf().is_file(), reason="MJCF not present")
def test_build_bc_dataset_arrays_shape() -> None:
    pytest.importorskip("mujoco")
    ref = _minimal_reference_29dof()
    cfg_pb = PlaybackConfig(
        mjcf_path=str(_mjcf()),
        sim_dt=0.005,
        mode="dynamic",
        kp=120.0,
        kd=4.0,
        seed=5,
        max_steps=8,
    )
    log = run_headless_playback(ref, cfg_pb)
    demo = build_demonstration_dataset(
        log,
        sim_dt=cfg_pb.sim_dt,
        seed=cfg_pb.seed,
        simulator_commit="x",
        include_ref=False,
    )
    obs_m, act_m, info = build_bc_dataset_arrays(demo, ref, include_imu=False)
    assert obs_m.shape == (8, 87)
    assert act_m.shape == (8, 29)
    assert np.all(act_m == 0.0)
    assert info["num_steps"] == 8
