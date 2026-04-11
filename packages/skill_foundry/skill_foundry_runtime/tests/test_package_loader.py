"""Skill package open from directory and tar.gz."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

from skill_foundry_runtime.package_loader import open_skill_package


def test_open_directory(tmp_path: Path) -> None:
    man = {"package_version": "1.0.0", "weights": {"filename": "w.zip"}}
    root = tmp_path / "p"
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (root / "w.zip").write_bytes(b"hi")

    with open_skill_package(root) as pkg:
        assert pkg.manifest["package_version"] == "1.0.0"
        assert pkg.weights_path().name == "w.zip"


def test_open_tarball(tmp_path: Path) -> None:
    man = {"package_version": "2.0.0", "weights": {"filename": "m.zip"}}
    root = tmp_path / "inner"
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (root / "m.zip").write_bytes(b"pk")

    out = tmp_path / "bundle.tar.gz"
    with tarfile.open(out, "w:gz") as tf:
        for p in root.iterdir():
            tf.add(p, arcname=p.name)

    with open_skill_package(out) as pkg:
        assert pkg.manifest["package_version"] == "2.0.0"
        assert pkg.weights_path().read_bytes() == b"pk"
