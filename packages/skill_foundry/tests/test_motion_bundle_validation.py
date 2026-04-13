"""Phase 6 motion skill bundle structural + MSE gate tests."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from skill_foundry_export.motion_bundle_validate import (
    validate_motion_skill_bundle,
)


def _write_minimal_bundle(
    out: Path,
    *,
    include_eval: bool = True,
    eval_metrics: dict | None = None,
    include_motion_manifest: bool = True,
) -> None:
    manifest = {
        "package_version": "1.0.0",
        "robot": {"profile": "unitree_g1_29dof"},
        "weights": {"filename": "ppo_G1TrackingEnv.zip"},
    }
    if include_motion_manifest:
        manifest["motion"] = {"reference_motion_source": "reference_trajectory.json"}

    ref = {
        "schema_version": "1.0.0",
        "robot_model": "g1_29dof",
        "units": {"angle": "radians", "time": "seconds"},
        "frequency_hz": 50.0,
        "root_model": "root_not_in_reference",
        "joint_order": ["0"],
        "joint_positions": [[0.0], [0.1]],
        "joint_velocities": [[0.0], [0.0]],
    }
    eval_obj = {
        "schema_version": "1.0",
        "metrics": eval_metrics or {"tracking_mean_mse": 0.01},
    }
    zip_bytes = b"PK\x03\x04fake"

    with tarfile.open(out, "w:gz") as tf:
        for name, data in (
            ("manifest.json", json.dumps(manifest).encode()),
            ("reference_trajectory.json", json.dumps(ref).encode()),
            ("ppo_G1TrackingEnv.zip", zip_bytes),
        ):
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            tf.addfile(ti, fileobj=__import__("io").BytesIO(data))
        if include_eval:
            raw = json.dumps(eval_obj).encode()
            ti = tarfile.TarInfo(name="eval_motion.json")
            ti.size = len(raw)
            tf.addfile(ti, fileobj=__import__("io").BytesIO(raw))


def test_motion_bundle_happy_path(tmp_path: Path) -> None:
    p = tmp_path / "b.tar.gz"
    _write_minimal_bundle(p)
    r = validate_motion_skill_bundle(p, require_motion_section=True, max_tracking_mse=1.0)
    assert r.passed, r.reasons


def test_motion_bundle_missing_eval(tmp_path: Path) -> None:
    p = tmp_path / "b.tar.gz"
    _write_minimal_bundle(p, include_eval=False)
    r = validate_motion_skill_bundle(p, require_motion_section=True)
    assert not r.passed
    assert any("eval_motion" in x for x in r.reasons)


def test_motion_bundle_mse_threshold(tmp_path: Path) -> None:
    p = tmp_path / "b.tar.gz"
    _write_minimal_bundle(p, eval_metrics={"tracking_mean_mse": 9.0})
    r = validate_motion_skill_bundle(p, require_motion_section=True, max_tracking_mse=0.5)
    assert not r.passed
    assert any("exceeds max" in x for x in r.reasons)
