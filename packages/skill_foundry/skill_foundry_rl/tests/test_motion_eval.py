"""Tests for AMP motion evaluation metrics and eval_motion.json contract."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from skill_foundry_rl.motion_eval import (
    EVAL_MOTION_SCHEMA_VERSION,
    RolloutBatch,
    build_eval_motion_report,
    compute_foot_sliding_proxy,
    compute_per_joint_mse,
    compute_velocity_mse,
    discriminator_realism_summary,
    motor_labels_from_joint_order,
    reference_motor_q_at_times,
    run_amp_eval,
)
from skill_foundry_rl.reference_motion import ReferenceMotion

_REPO = Path(__file__).resolve().parents[4]
_MJCF = _REPO / "unitree_mujoco" / "unitree_robots" / "g1" / "scene_29dof.xml"
_REF = _REPO / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"


def test_compute_per_joint_mse_identical() -> None:
    q = np.random.randn(10, 29).astype(np.float64)
    per, mean = compute_per_joint_mse(q, q.copy())
    assert mean == pytest.approx(0.0, abs=1e-12)
    assert np.all(per == pytest.approx(0.0, abs=1e-12))


def test_compute_per_joint_mse_known() -> None:
    a = np.zeros((2, 29), dtype=np.float64)
    b = np.zeros((2, 29), dtype=np.float64)
    b[:, 0] = 1.0
    per, mean = compute_per_joint_mse(a, b)
    assert per[0] == pytest.approx(1.0)
    assert per[1] == pytest.approx(0.0)
    assert mean == pytest.approx(1.0 / 29.0)


def test_compute_foot_sliding_proxy() -> None:
    q = np.zeros((4, 29), dtype=np.float64)
    assert compute_foot_sliding_proxy(q, dt=0.01) is not None
    out = compute_foot_sliding_proxy(q, dt=0.01)
    assert out is not None
    assert out["method"] == "ankle_velocity_energy"
    assert out["mean_sq_velocity"] == pytest.approx(0.0, abs=1e-12)
    q[:, 4] = np.linspace(0, 1, 4)
    out2 = compute_foot_sliding_proxy(q, dt=0.01)
    assert out2 is not None
    assert out2["mean_sq_velocity"] > 0


def test_compute_velocity_mse() -> None:
    t = 5
    q0 = np.zeros((t, 29))
    q1 = np.zeros((t, 29))
    for i in range(t):
        q0[i] = i * 0.1
        q1[i] = i * 0.1
    assert compute_velocity_mse(q0, q1, dt=0.01) == pytest.approx(0.0)
    q2 = q0.copy()
    q2[:, 0] += 0.5
    v = compute_velocity_mse(q0, q2, dt=0.01)
    assert v is not None and v > 0


def test_motor_labels_from_joint_order() -> None:
    labels = motor_labels_from_joint_order(["5", "10"])
    assert labels[5] == "5"
    assert labels[10] == "10"


def test_discriminator_realism_summary() -> None:
    pytest.importorskip("torch")
    from skill_foundry_rl.amp_discriminator import AMPDiscriminator
    from skill_foundry_rl.obs_schema import rl_obs_dim

    dim = rl_obs_dim(include_imu=False)
    disc = AMPDiscriminator(state_dim=dim, hidden_dim=32, num_layers=2)
    n = 8
    obs = np.random.randn(n, dim).astype(np.float32)
    nxt = np.random.randn(n, dim).astype(np.float32)
    s = discriminator_realism_summary(disc, obs, nxt, batch=4)
    assert s["count"] == n
    assert s["mean_amp_reward"] is not None


def test_build_eval_motion_report_contract() -> None:
    pytest.importorskip("torch")
    ref = ReferenceMotion(
        frequency_hz=50.0,
        joint_order=["0", "1"],
        joint_positions=[[0.0, 0.0]] * 20,
        joint_velocities=[[0.0, 0.0]] * 20,
    )
    times = np.array([0.02 * (i + 1) for i in range(5)], dtype=np.float64)
    ref_q = reference_motor_q_at_times(ref, times)
    rq = ref_q + 0.01
    dim = 87
    rollout = RolloutBatch(
        times_s=times,
        motor_q=rq.astype(np.float64),
        obs=np.random.randn(len(times), dim).astype(np.float64),
        next_obs=np.random.randn(len(times), dim).astype(np.float64),
    )
    report = build_eval_motion_report(
        reference_sha256="a" * 64,
        checkpoint="/tmp/ckpt.zip",
        joint_order=["0", "1"],
        rollout=rollout,
        ref=ref,
        sim_dt=0.02,
        discriminator_path=None,
        amp_cfg=None,
    )
    required = (
        "schema_version",
        "created_at",
        "reference_sha256",
        "checkpoint",
        "rollout_steps",
        "metrics",
        "notes",
    )
    for k in required:
        assert k in report
    assert report["schema_version"] == EVAL_MOTION_SCHEMA_VERSION
    m = report["metrics"]
    assert "tracking_mean_mse" in m
    assert "tracking_per_joint_mse" in m
    assert "velocity_mse" in m
    assert "foot_sliding" in m
    fs = m["foot_sliding"]
    assert isinstance(fs, dict)
    assert fs.get("method") == "ankle_velocity_energy"
    assert "mean_sq_velocity" in fs
    assert len(m["tracking_per_joint_mse"]) == 29


@pytest.mark.skipif(not _MJCF.is_file(), reason="unitree_mujoco scene not present")
@pytest.mark.skipif(not _REF.is_file(), reason="golden reference not present")
def test_run_amp_eval_end_to_end() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("stable_baselines3")
    import tempfile

    from skill_foundry_rl.amp_train import run_amp_train

    cfg = {
        "seed": 7,
        "env": {
            "mjcf_path": str(_MJCF),
            "sim_dt": 0.005,
            "min_base_height": 0.2,
            "max_episode_steps": 64,
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
        "motion_eval": {"rollout_max_steps": 32},
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        run_amp_train(reference_path=_REF, config=cfg, output_dir=out)
        ckpt = Path(json.loads((out / "train_run.json").read_text(encoding="utf-8"))["checkpoint"])
        eval_out = out / "eval_motion.json"
        run_amp_eval(
            reference_path=_REF,
            config=cfg,
            checkpoint_path=ckpt,
            output_path=eval_out,
            seed=1,
        )
        assert eval_out.is_file()
        data = json.loads(eval_out.read_text(encoding="utf-8"))
        assert data["schema_version"] == EVAL_MOTION_SCHEMA_VERSION
        assert data["rollout_steps"] > 0
        assert "discriminator" in data["metrics"]
