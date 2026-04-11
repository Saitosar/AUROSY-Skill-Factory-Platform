"""Short PPO run for CI / DoD smoke (thresholds: run completes, checkpoint written)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_foundry_rl.ppo_train import run_ppo_train

_REPO = Path(__file__).resolve().parents[4]
_MJCF = _REPO / "unitree_mujoco" / "unitree_robots" / "g1" / "scene_29dof.xml"
_REF = _REPO / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"


@pytest.mark.skipif(not _MJCF.is_file(), reason="unitree_mujoco scene not present")
@pytest.mark.skipif(not _REF.is_file(), reason="golden reference not present")
def test_ppo_train_minimal_writes_checkpoint() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("stable_baselines3")
    import tempfile

    cfg = {
        "seed": 1,
        "env": {
            "mjcf_path": str(_MJCF),
            "sim_dt": 0.005,
            "min_base_height": 0.2,
            "max_episode_steps": 200,
        },
        "ppo": {
            "learning_rate": 3e-4,
            "n_steps": 128,
            "batch_size": 64,
            "n_epochs": 2,
            "total_timesteps": 256,
        },
        "early_stop": {"eval_freq": 0, "plateau_patience": 0},
        "product_validation": {"enabled": False},
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        payload = run_ppo_train(reference_path=_REF, config=cfg, output_dir=out)
        assert payload["status"] == "ok"
        assert payload["obs_schema_ref"] == "skill_foundry_rl_tracking_v1"
        ck = Path(payload["checkpoint"])
        assert ck.is_file()
        run = json.loads((out / "train_run.json").read_text(encoding="utf-8"))
        assert run["total_timesteps_trained"] >= 256
        assert run.get("mjcf_sha256")
        assert run.get("env_snapshot", {}).get("mjcf_path")
