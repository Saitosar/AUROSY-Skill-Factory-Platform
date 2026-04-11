"""Reproducibility: two headless runs with the same seed produce identical logs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mujoco")

from skill_foundry_sim.headless_playback import PlaybackConfig, run_headless_playback
from skill_foundry_sim.log_compare import compare_playback_logs


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _mjcf_path() -> Path:
    p = _repo_root() / "unitree_mujoco/unitree_robots/g1/scene_29dof.xml"
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


def test_dynamic_playback_reproducible():
    ref = _minimal_reference_29dof()
    cfg = PlaybackConfig(
        mjcf_path=str(_mjcf_path()),
        sim_dt=0.005,
        mode="dynamic",
        kp=120.0,
        kd=4.0,
        seed=42,
        max_steps=40,
    )
    a = run_headless_playback(ref, cfg)
    b = run_headless_playback(ref, cfg)
    ok, msgs = compare_playback_logs(a, b, atol=1e-9, rtol=1e-9)
    assert ok, msgs


def test_kinematic_playback_reproducible():
    ref = _minimal_reference_29dof()
    cfg = PlaybackConfig(
        mjcf_path=str(_mjcf_path()),
        sim_dt=0.005,
        mode="kinematic",
        seed=7,
        max_steps=25,
    )
    a = run_headless_playback(ref, cfg)
    b = run_headless_playback(ref, cfg)
    ok, msgs = compare_playback_logs(a, b, atol=1e-9, rtol=1e-9)
    assert ok, msgs


def test_trajectory_sampler_clip():
    from skill_foundry_sim.trajectory_sampler import sample_trajectory_at_times

    jp = [[0.0], [1.0]]
    t = np.asarray([100.0])  # beyond trajectory

    q, dq = sample_trajectory_at_times(jp, frequency_hz=10.0, sample_times_s=t)
    assert q.shape == (1, 1)
    assert float(q[0, 0]) == 1.0
