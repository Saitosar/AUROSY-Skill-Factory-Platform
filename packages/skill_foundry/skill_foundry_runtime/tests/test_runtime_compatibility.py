"""Compatibility checks for manifest vs MJCF and reference."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_foundry_export.manifest import build_manifest
from skill_foundry_runtime.compatibility import check_compatibility, sha256_file


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


def test_mjcf_sha_mismatch_reported(tmp_path: Path) -> None:
    root = _repo()
    ref_path = root / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))

    mjcf_train = tmp_path / "train.xml"
    mjcf_train.write_bytes(b"<mujoco><worldbody/></mujoco>")
    mjcf_wrong = tmp_path / "other.xml"
    mjcf_wrong.write_bytes(b"<mujoco><worldbody><geom name='x'/></worldbody></mujoco>")

    cfg = {
        "env": {
            "mjcf_path": str(mjcf_train.resolve()),
            "sim_dt": 0.005,
            "include_imu_in_obs": False,
        }
    }
    train_run = {
        "reference_sha256": sha256_file(ref_path),
        "mjcf_sha256": sha256_file(mjcf_train),
    }
    man = build_manifest(
        train_config=cfg,
        reference=ref,
        train_run=train_run,
    )

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (pkg / "ppo_G1TrackingEnv.zip").write_bytes(b"x")

    errs = check_compatibility(
        man,
        package_root=pkg,
        mjcf_path=mjcf_wrong,
        reference_path=ref_path,
        expected_profile=None,
        allow_missing_weights_sha256=True,
    )
    assert any("mjcf_sha256 mismatch" in e for e in errs)


def test_reference_sha_mismatch_reported(tmp_path: Path) -> None:
    root = _repo()
    ref_path = root / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))

    mjcf = tmp_path / "scene.xml"
    mjcf.write_bytes(b"<mujoco><worldbody/></mujoco>")

    cfg = {
        "env": {
            "mjcf_path": str(mjcf.resolve()),
            "sim_dt": 0.005,
            "include_imu_in_obs": False,
        }
    }
    train_run = {
        "reference_sha256": "a" * 64,
        "mjcf_sha256": sha256_file(mjcf),
    }
    man = build_manifest(
        train_config=cfg,
        reference=ref,
        train_run=train_run,
    )

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (pkg / "ppo_G1TrackingEnv.zip").write_bytes(b"x")

    errs = check_compatibility(
        man,
        package_root=pkg,
        mjcf_path=mjcf,
        reference_path=ref_path,
        expected_profile=None,
        allow_missing_weights_sha256=True,
    )
    assert any("reference_sha256 mismatch" in e for e in errs)


def test_weights_sha256_mismatch_reported(tmp_path: Path) -> None:
    root = _repo()
    ref_path = root / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))

    mjcf = tmp_path / "scene.xml"
    mjcf.write_bytes(b"<mujoco><worldbody/></mujoco>")

    cfg = {
        "env": {
            "mjcf_path": str(mjcf.resolve()),
            "sim_dt": 0.005,
            "include_imu_in_obs": False,
        }
    }
    train_run = {
        "reference_sha256": sha256_file(ref_path),
        "mjcf_sha256": sha256_file(mjcf),
    }
    man = build_manifest(
        train_config=cfg,
        reference=ref,
        train_run=train_run,
    )
    man["weights"]["sha256"] = "0" * 64

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (pkg / "ppo_G1TrackingEnv.zip").write_bytes(b"not-matching-weights")

    errs = check_compatibility(
        man,
        package_root=pkg,
        mjcf_path=mjcf,
        reference_path=ref_path,
        expected_profile=None,
    )
    assert any("weights.sha256 mismatch" in e for e in errs)


def test_missing_weights_sha256_reported_when_strict(tmp_path: Path) -> None:
    root = _repo()
    ref_path = root / "docs" / "skill_foundry" / "golden" / "v1" / "reference_trajectory.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))

    mjcf = tmp_path / "scene.xml"
    mjcf.write_bytes(b"<mujoco><worldbody/></mujoco>")

    cfg = {
        "env": {
            "mjcf_path": str(mjcf.resolve()),
            "sim_dt": 0.005,
            "include_imu_in_obs": False,
        }
    }
    train_run = {
        "reference_sha256": sha256_file(ref_path),
        "mjcf_sha256": sha256_file(mjcf),
    }
    man = build_manifest(
        train_config=cfg,
        reference=ref,
        train_run=train_run,
    )
    if "sha256" in man.get("weights", {}):
        del man["weights"]["sha256"]

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (pkg / "ppo_G1TrackingEnv.zip").write_bytes(b"x")

    errs = check_compatibility(
        man,
        package_root=pkg,
        mjcf_path=mjcf,
        reference_path=ref_path,
        expected_profile=None,
        allow_missing_weights_sha256=False,
    )
    assert any("weights.sha256 missing" in e for e in errs)
