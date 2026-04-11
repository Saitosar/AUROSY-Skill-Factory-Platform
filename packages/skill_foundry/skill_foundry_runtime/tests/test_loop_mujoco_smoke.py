"""Short MuJoCo loop without loading SB3 (action_fn)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from skill_foundry_export.manifest import build_manifest
from skill_foundry_runtime.loop_mujoco import run_mujoco_skill_loop
from skill_foundry_sim.reference_loader import load_reference_trajectory_json

_REPO = Path(__file__).resolve().parents[4]
_MJCF = _REPO / "unitree_mujoco" / "unitree_robots" / "g1" / "scene_29dof.xml"
_REF = _REPO / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"


@pytest.mark.skipif(not _MJCF.is_file(), reason="unitree_mujoco scene not present")
@pytest.mark.skipif(not _REF.is_file(), reason="golden reference not present")
def test_mujoco_loop_zero_action_smoke() -> None:
    pytest.importorskip("gymnasium")
    ref = load_reference_trajectory_json(_REF)
    cfg = {
        "env": {
            "mjcf_path": str(_MJCF.resolve()),
            "sim_dt": 0.005,
            "delta_max": 0.25,
            "kp": 150.0,
            "kd": 5.0,
            "include_imu_in_obs": False,
        }
    }
    man = build_manifest(train_config=cfg, reference=ref, train_run=None)

    def zeros(obs: np.ndarray) -> np.ndarray:
        return np.zeros(29, dtype=np.float64)

    res = run_mujoco_skill_loop(
        mjcf_path=str(_MJCF),
        reference=ref,
        manifest=man,
        policy=None,
        max_steps=20,
        action_fn=zeros,
        min_base_height=0.05,
    )
    # Golden reference has 2 samples at 50 Hz → t_max=0.02 s; dt=0.005 → 5 steps to end.
    assert res.steps == 5
    assert not res.stopped
