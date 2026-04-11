"""Open a skill package directory or .tar.gz archive."""

from __future__ import annotations

import json
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillPackage:
    """Resolved package root (directory with ``manifest.json``)."""

    root: Path
    manifest: dict[str, Any]
    _tempdir: tempfile.TemporaryDirectory[str] | None = field(default=None, repr=False)

    def weights_path(self) -> Path:
        name = self.manifest["weights"]["filename"]
        return self.root / name

    def close(self) -> None:
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None

    def __enter__(self) -> SkillPackage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _load_manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"manifest.json not found under {root}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest.json must contain a JSON object")
    return data


def open_skill_package(path: Path | str) -> SkillPackage:
    """
    Load package from a directory (already extracted) or from ``.tar.gz``.

    When extracting an archive, a temporary directory is used; call
    :meth:`SkillPackage.close` or use a context manager when done.
    """
    p = Path(path).expanduser().resolve()
    if p.is_dir():
        return SkillPackage(root=p, manifest=_load_manifest(p), _tempdir=None)

    if not p.is_file():
        raise FileNotFoundError(f"package path not found: {p}")

    td = tempfile.TemporaryDirectory(prefix="skill_foundry_pkg_")
    root = Path(td.name)
    try:
        with tarfile.open(p, "r:*") as tf:
            if sys.version_info >= (3, 12):
                tf.extractall(root, filter="data")
            else:
                tf.extractall(root)
    except Exception:
        td.cleanup()
        raise
    return SkillPackage(root=root, manifest=_load_manifest(root), _tempdir=td)
