"""PPO train with optional BC pretrain (Phase 3.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_foundry_rl.ppo_train import run_ppo_train
from skill_foundry_sim.demonstration_dataset import build_demonstration_dataset, write_demonstration_dataset_json
from skill_foundry_sim.headless_playback import PlaybackConfig, run_headless_playback
from skill_foundry_sim.reference_loader import load_reference_trajectory_json


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


def _mjcf() -> Path:
    p = _repo() / "unitree_mujoco" / "unitree_robots" / "g1" / "scene_29dof.xml"
    if not p.is_file():
        pytest.skip(f"MJCF not found: {p}")
    return p


def _ref() -> Path:
    p = _repo() / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"
    if not p.is_file():
        pytest.skip("golden reference not present")
    return p


@pytest.mark.skipif(not _mjcf().is_file(), reason="MJCF not present")
@pytest.mark.skipif(not _ref().is_file(), reason="golden reference not present")
def test_ppo_train_with_bc_pretrain_completes() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("stable_baselines3")
    pytest.importorskip("mujoco")
    import tempfile

    ref = load_reference_trajectory_json(_ref())
    cfg_pb = PlaybackConfig(
        mjcf_path=str(_mjcf()),
        sim_dt=0.005,
        mode="dynamic",
        kp=150.0,
        kd=5.0,
        seed=99,
        max_steps=24,
    )
    log = run_headless_playback(ref, cfg_pb)
    demo = build_demonstration_dataset(
        log,
        robot_model="g1_29dof",
        sim_dt=cfg_pb.sim_dt,
        seed=cfg_pb.seed,
        simulator_commit="test_bc",
        include_ref=True,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        demo_path = tmp_path / "demonstration_dataset.json"
        write_demonstration_dataset_json(demo_path, demo)

        cfg = {
            "seed": 2,
            "bc": {
                "enabled": True,
                "epochs": 2,
                "batch_size": 32,
                "learning_rate": 0.01,
            },
            "env": {
                "mjcf_path": str(_mjcf()),
                "sim_dt": 0.005,
                "min_base_height": 0.2,
                "max_episode_steps": 200,
                "include_imu_in_obs": False,
            },
            "ppo": {
                "learning_rate": 3e-4,
                "n_steps": 128,
                "batch_size": 64,
                "n_epochs": 2,
                "total_timesteps": 128,
            },
            "early_stop": {"eval_freq": 0, "plateau_patience": 0},
        }
        out = tmp_path / "out"
        payload = run_ppo_train(
            reference_path=_ref(),
            config=cfg,
            output_dir=out,
            demonstration_path=demo_path,
        )
        assert payload["status"] == "ok"
        assert payload["phase"] == "3.3_ppo_bc"
        assert "bc" in payload
        assert payload["bc"]["bc_epochs"] == 2
        assert payload["bc"]["num_steps"] == 24
        run = json.loads((out / "train_run.json").read_text(encoding="utf-8"))
        assert run["phase"] == "3.3_ppo_bc"
        assert "bc" in run
