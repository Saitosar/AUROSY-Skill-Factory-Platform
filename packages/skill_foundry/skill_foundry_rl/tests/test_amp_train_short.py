"""Short AMP run for CI / DoD smoke."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_foundry_rl.amp_train import run_amp_train

_REPO = Path(__file__).resolve().parents[4]
_MJCF = _REPO / "unitree_mujoco" / "unitree_robots" / "g1" / "scene_29dof.xml"
_REF = _REPO / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"


@pytest.mark.skipif(not _MJCF.is_file(), reason="unitree_mujoco scene not present")
@pytest.mark.skipif(not _REF.is_file(), reason="golden reference not present")
def test_amp_train_minimal_outputs() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("stable_baselines3")
    import tempfile

    cfg = {
        "seed": 3,
        "env": {
            "mjcf_path": str(_MJCF),
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
            "total_timesteps": 256,
        },
        "amp": {
            "disc_hidden_dim": 64,
            "disc_num_layers": 2,
            "disc_updates_per_iter": 1,
            "policy_chunk_timesteps": 128,
            "policy_rollout_steps": 64,
        },
        "product_validation": {"enabled": False},
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        payload = run_amp_train(reference_path=_REF, config=cfg, output_dir=out)
        assert payload["status"] == "ok"
        assert payload["phase"] == "4_amp"
        assert payload["obs_schema_ref"] == "skill_foundry_rl_tracking_v1"
        assert Path(payload["checkpoint"]).is_file()
        assert Path(payload["amp_discriminator_checkpoint"]).is_file()
        run = json.loads((out / "train_run.json").read_text(encoding="utf-8"))
        assert run["total_timesteps_trained"] >= 256
        assert run["amp"]["metrics"]
