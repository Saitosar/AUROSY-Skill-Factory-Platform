"""Validate motion skill bundles (Phase 6): required members, optional eval thresholds."""

from __future__ import annotations

import json
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MotionBundleValidationResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def _read_json_from_tar(tf: tarfile.TarFile, name: str) -> dict[str, Any] | None:
    for m in tf.getmembers():
        if m.isfile() and (m.name == name or m.name.endswith("/" + name)):
            f = tf.extractfile(m)
            if f is None:
                return None
            try:
                return json.loads(f.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
    return None


def _member_names(tf: tarfile.TarFile) -> set[str]:
    return {m.name for m in tf.getmembers() if m.isfile()}


def read_manifest_from_tarball(tarball: Path) -> dict[str, Any] | None:
    """Return parsed ``manifest.json`` from a skill bundle ``.tar.gz``, or ``None``."""
    path = tarball.expanduser().resolve()
    if not path.is_file():
        return None
    try:
        with tarfile.open(path, "r:*") as tf:
            m = _read_json_from_tar(tf, "manifest.json")
            return m if isinstance(m, dict) else None
    except (OSError, tarfile.TarError):
        return None


def validate_motion_skill_bundle(
    tarball: Path,
    *,
    require_motion_section: bool = False,
    max_tracking_mse: float | None = None,
) -> MotionBundleValidationResult:
    """
    Check tarball for skill bundle integrity.

    - Always requires ``manifest.json`` and ``reference_trajectory.json``.
    - Weights file: uses ``manifest['weights']['filename']`` when present.
    - When ``require_motion_section`` is True or ``manifest`` contains ``motion``,
      ``eval_motion.json`` must be present and parseable.
    - When ``max_tracking_mse`` is set, ``metrics.tracking_mean_mse`` must be <= limit.
    """
    reasons: list[str] = []
    metrics: dict[str, Any] = {}

    path = tarball.expanduser().resolve()
    if not path.is_file():
        return MotionBundleValidationResult(False, [f"bundle not found: {path}"], metrics)

    try:
        tf = tarfile.open(path, "r:*")
    except tarfile.TarError as e:
        return MotionBundleValidationResult(False, [f"invalid tarball: {e}"], metrics)

    with tf:
        names = _member_names(tf)
        base_names = {n.split("/")[-1] for n in names}

        if "manifest.json" not in base_names:
            reasons.append("missing manifest.json")
        if "reference_trajectory.json" not in base_names:
            reasons.append("missing reference_trajectory.json")

        manifest = _read_json_from_tar(tf, "manifest.json")
        if not isinstance(manifest, dict):
            reasons.append("manifest.json missing or invalid JSON")
            return MotionBundleValidationResult(False, reasons, metrics)

        wname = manifest.get("weights")
        wfile = None
        if isinstance(wname, dict):
            wfile = wname.get("filename")
        if isinstance(wfile, str):
            if wfile not in base_names:
                reasons.append(f"weights file {wfile!r} not in archive")
        else:
            reasons.append("manifest.weights.filename missing")

        motion = manifest.get("motion")
        need_eval = bool(require_motion_section) or isinstance(motion, dict)
        if need_eval:
            if "eval_motion.json" not in base_names:
                reasons.append("motion bundle requires eval_motion.json in archive")
            else:
                eval_data = _read_json_from_tar(tf, "eval_motion.json")
                if not isinstance(eval_data, dict):
                    reasons.append("eval_motion.json missing or invalid JSON")
                else:
                    m = eval_data.get("metrics")
                    if isinstance(m, dict):
                        metrics = dict(m)
                    tmm = (eval_data.get("metrics") or {}).get("tracking_mean_mse")
                    if tmm is None:
                        reasons.append("eval_motion.json missing metrics.tracking_mean_mse")
                    elif max_tracking_mse is not None and float(tmm) > float(max_tracking_mse):
                        reasons.append(
                            f"tracking_mean_mse {float(tmm):.6g} exceeds max {float(max_tracking_mse):.6g}",
                        )

    if reasons:
        return MotionBundleValidationResult(False, reasons, metrics)
    return MotionBundleValidationResult(True, [], metrics)
