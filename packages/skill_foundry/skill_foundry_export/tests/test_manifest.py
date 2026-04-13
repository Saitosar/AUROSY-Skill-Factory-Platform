"""Tests for export manifest and packaging."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from skill_foundry_export.manifest import build_manifest, build_observation_blocks
from skill_foundry_export.packaging import package_skill
from skill_foundry_export.validate import validate_export_manifest_dict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_observation_blocks_no_imu() -> None:
    blocks, dim = build_observation_blocks(include_imu=False)
    assert dim == 87
    assert blocks[0]["length"] == 29
    assert blocks[-1]["offset"] + blocks[-1]["length"] == 87


def test_observation_blocks_with_imu() -> None:
    blocks, dim = build_observation_blocks(include_imu=True)
    assert dim == 100
    assert blocks[-1]["name"] == "imu"
    assert blocks[-1]["length"] == 13


def test_build_manifest_matches_schema() -> None:
    root = _repo_root()
    ref_path = root / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))

    mjcf = root / "packages" / "skill_foundry" / "skill_foundry_export" / "tests" / "fixtures" / "dummy_scene.xml"
    mjcf.parent.mkdir(parents=True, exist_ok=True)
    mjcf.write_text("<mujoco model='dummy'><worldbody/></mujoco>\n", encoding="utf-8")

    cfg = {
        "env": {
            "mjcf_path": str(mjcf.resolve()),
            "sim_dt": 0.005,
            "delta_max": 0.25,
            "kp": 150.0,
            "kd": 5.0,
            "include_imu_in_obs": False,
        }
    }

    import hashlib

    def _sha256(p: Path) -> str:
        h = hashlib.sha256()
        h.update(p.read_bytes())
        return h.hexdigest()

    train_run = {
        "reference_sha256": _sha256(ref_path),
        "mjcf_sha256": _sha256(mjcf),
        "phase": "3.2_ppo",
    }

    man = build_manifest(
        train_config=cfg,
        reference=ref,
        train_run=train_run,
        train_config_path=root / "docs" / "skill_foundry" / "golden" / "v1" / "ppo_train_config.example.json",
    )
    errs = validate_export_manifest_dict(man)
    assert errs == [], errs


def test_package_skill_tarball(tmp_path: Path) -> None:
    root = _repo_root()
    ref_path = root / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"

    mjcf = tmp_path / "scene.xml"
    mjcf.write_bytes(b"<mujoco><worldbody/></mujoco>")

    cfg = {
        "env": {
            "mjcf_path": str(mjcf),
            "sim_dt": 0.005,
            "include_imu_in_obs": False,
        }
    }

    import hashlib

    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    ref_bytes = ref_path.read_bytes()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ckpt = run_dir / "ppo_G1TrackingEnv.zip"
    ckpt.write_bytes(b"PK\x03\x04fake_zip_bytes")

    train_run = {
        "reference_sha256": _sha256_bytes(ref_bytes),
        "mjcf_sha256": _sha256_bytes(mjcf.read_bytes()),
        "checkpoint": str(ckpt),
    }
    (run_dir / "train_run.json").write_text(json.dumps(train_run), encoding="utf-8")

    out = tmp_path / "bundle.tar.gz"
    tc_path = tmp_path / "train.json"
    tc_path.write_text(json.dumps(cfg), encoding="utf-8")

    summary = package_skill(
        train_config=cfg,
        reference_path=ref_path,
        run_dir=run_dir,
        output_archive=out,
        train_config_path=tc_path,
    )
    assert out.is_file()
    assert "manifest.json" in summary["files"]

    with tarfile.open(out, "r:gz") as tf:
        names = tf.getnames()
        assert "manifest.json" in names
        assert "ppo_G1TrackingEnv.zip" in names
        assert "reference_trajectory.json" in names
        man = json.loads(tf.extractfile("manifest.json").read().decode("utf-8"))
        assert man.get("reference_trajectory", {}).get("filename") == "reference_trajectory.json"
    errs = validate_export_manifest_dict(man)
    assert errs == [], errs


def test_package_skill_includes_validation_report(tmp_path: Path) -> None:
    root = _repo_root()
    ref_path = root / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"

    mjcf = tmp_path / "scene.xml"
    mjcf.write_bytes(b"<mujoco><worldbody/></mujoco>")

    cfg = {
        "env": {
            "mjcf_path": str(mjcf),
            "sim_dt": 0.005,
            "include_imu_in_obs": False,
        }
    }

    import hashlib

    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    ref_bytes = ref_path.read_bytes()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ckpt = run_dir / "ppo_G1TrackingEnv.zip"
    ckpt.write_bytes(b"PK\x03\x04fake_zip_bytes")

    train_run = {
        "reference_sha256": _sha256_bytes(ref_bytes),
        "mjcf_sha256": _sha256_bytes(mjcf.read_bytes()),
        "checkpoint": str(ckpt),
    }
    (run_dir / "train_run.json").write_text(json.dumps(train_run), encoding="utf-8")
    val_rep = {
        "validation_report_schema_ref": "skill_foundry_product_validation_report_v1",
        "applicable": True,
        "passed": True,
        "metrics": {"mean_tracking_error_mse": 0.01, "fall_episodes": 0, "n_episodes": 5},
    }
    (run_dir / "validation_report.json").write_text(json.dumps(val_rep), encoding="utf-8")

    out = tmp_path / "bundle.tar.gz"
    tc_path = tmp_path / "train.json"
    tc_path.write_text(json.dumps(cfg), encoding="utf-8")

    summary = package_skill(
        train_config=cfg,
        reference_path=ref_path,
        run_dir=run_dir,
        output_archive=out,
        train_config_path=tc_path,
    )
    assert "validation_report.json" in summary["files"]

    with tarfile.open(out, "r:gz") as tf:
        names = tf.getnames()
        assert "validation_report.json" in names
        man = json.loads(tf.extractfile("manifest.json").read().decode("utf-8"))
        pv = man.get("product_validation")
        assert isinstance(pv, dict)
        assert pv.get("passed") is True
        assert pv.get("filename") == "validation_report.json"
    errs = validate_export_manifest_dict(man)
    assert errs == [], errs


def test_package_skill_includes_eval_motion_and_motion_manifest(tmp_path: Path) -> None:
    root = _repo_root()
    ref_path = root / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"

    mjcf = tmp_path / "scene.xml"
    mjcf.write_bytes(b"<mujoco><worldbody/></mujoco>")

    cfg = {
        "env": {
            "mjcf_path": str(mjcf),
            "sim_dt": 0.005,
            "include_imu_in_obs": False,
        }
    }

    import hashlib

    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    ref_bytes = ref_path.read_bytes()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ckpt = run_dir / "ppo_amp_G1TrackingEnv.zip"
    ckpt.write_bytes(b"PK\x03\x04fake_zip_bytes")

    train_run = {
        "reference_sha256": _sha256_bytes(ref_bytes),
        "mjcf_sha256": _sha256_bytes(mjcf.read_bytes()),
        "checkpoint": str(ckpt),
        "phase": "4_amp",
        "amp": {"disc_hidden_dim": 64, "disc_num_layers": 2},
    }
    (run_dir / "train_run.json").write_text(json.dumps(train_run), encoding="utf-8")
    eval_body = {
        "schema_version": "1.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "reference_sha256": "a" * 64,
        "checkpoint": str(ckpt),
        "rollout_steps": 5,
        "metrics": {"tracking_mean_mse": 0.1},
        "notes": "test",
    }
    (run_dir / "eval_motion.json").write_text(json.dumps(eval_body), encoding="utf-8")
    disc = run_dir / "amp_discriminator.pt"
    disc.write_bytes(b"torch_state_dict_placeholder")

    out = tmp_path / "bundle.tar.gz"
    tc_path = tmp_path / "train.json"
    tc_path.write_text(json.dumps(cfg), encoding="utf-8")

    summary = package_skill(
        train_config=cfg,
        reference_path=ref_path,
        run_dir=run_dir,
        output_archive=out,
        train_config_path=tc_path,
        include_amp_discriminator=True,
    )
    assert "eval_motion.json" in summary["files"]
    assert "amp_discriminator.pt" in summary["files"]
    man = summary["manifest"]
    assert "motion" in man
    assert man["motion"]["eval_report"]["filename"] == "eval_motion.json"
    assert man["motion"]["amp"]["discriminator_bundle_filename"] == "amp_discriminator.pt"
    errs = validate_export_manifest_dict(man)
    assert errs == [], errs
