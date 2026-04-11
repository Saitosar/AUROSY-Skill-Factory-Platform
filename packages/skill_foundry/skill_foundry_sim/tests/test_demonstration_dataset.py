"""DemonstrationDataset v1 from headless playback."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mujoco")

from skill_foundry_phase0.contract_validator import validate_demonstration_dataset_dict
from skill_foundry_sim.demonstration_dataset import (
    OBS_SCHEMA_REF,
    build_demonstration_dataset,
)
from skill_foundry_sim.headless_playback import PlaybackConfig, run_headless_playback


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


def test_demonstration_dataset_from_dynamic_playback():
    ref = _minimal_reference_29dof()
    cfg = PlaybackConfig(
        mjcf_path=str(_mjcf_path()),
        sim_dt=0.005,
        mode="dynamic",
        kp=120.0,
        kd=4.0,
        seed=11,
        max_steps=30,
    )
    log = run_headless_playback(ref, cfg)
    demo = build_demonstration_dataset(
        log,
        robot_model="g1_29dof",
        sim_dt=cfg.sim_dt,
        seed=cfg.seed,
        simulator_commit="test_commit",
        include_ref=True,
    )
    assert demo["obs_schema_ref"] == OBS_SCHEMA_REF
    assert demo["sampling_hz"] == pytest.approx(200.0)
    assert demo["seed"] == 11
    assert demo["simulator_commit"] == "test_commit"
    ep = demo["episodes"][0]
    assert ep["episode_id"] == "ep_0001"
    steps = ep["steps"]
    assert len(steps) == 30
    assert len(steps[0]["obs"]) == 58
    assert len(steps[0]["act"]) == 29
    assert len(steps[0]["ref"]) == 29
    assert steps[-1]["done"] is True
    assert sum(1 for s in steps if s["done"]) == 1
    assert validate_demonstration_dataset_dict(demo) == []


def test_demonstration_dataset_no_ref():
    ref = _minimal_reference_29dof()
    cfg = PlaybackConfig(
        mjcf_path=str(_mjcf_path()),
        sim_dt=0.005,
        mode="kinematic",
        seed=3,
        max_steps=12,
    )
    log = run_headless_playback(ref, cfg)
    demo = build_demonstration_dataset(
        log,
        sim_dt=cfg.sim_dt,
        seed=cfg.seed,
        simulator_commit="abc",
        include_ref=False,
    )
    assert "ref" not in demo["episodes"][0]["steps"][0]
    assert validate_demonstration_dataset_dict(demo) == []
