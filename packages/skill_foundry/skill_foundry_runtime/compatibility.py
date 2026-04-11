"""Manifest vs local MJCF, reference file, and package contents."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from skill_foundry_export.packaging import REFERENCE_BUNDLE_FILENAME
from skill_foundry_export.validate import validate_export_manifest_dict
from skill_foundry_rl.obs_schema import rl_obs_dim


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_reference_path(
    package_root: Path,
    manifest: dict[str, Any],
    override: Path | None,
) -> Path:
    """Bundled reference from manifest, or ``override`` path (must exist)."""
    if override is not None:
        op = override.expanduser().resolve()
        if not op.is_file():
            raise FileNotFoundError(f"reference trajectory not found: {op}")
        return op
    rt = manifest.get("reference_trajectory") or {}
    fn = rt.get("filename") if isinstance(rt, dict) else None
    if not isinstance(fn, str) or not fn:
        fn = REFERENCE_BUNDLE_FILENAME
    p = package_root / fn
    if not p.is_file():
        raise FileNotFoundError(
            f"bundled reference missing ({fn}); re-pack with Phase 4.1 or pass --reference"
        )
    return p


def check_compatibility(
    manifest: dict[str, Any],
    *,
    package_root: Path,
    mjcf_path: Path,
    reference_path: Path,
    expected_profile: str | None = None,
    allow_missing_weights_sha256: bool = False,
) -> list[str]:
    """
    Return human-readable errors; empty list means checks passed.

    Validates JSON Schema (when ``jsonschema`` is installed), artifact presence,
    SHA-256 of MJCF and reference vs manifest provenance, SHA-256 of weights file
    when ``manifest.weights.sha256`` is set (or required unless
    ``allow_missing_weights_sha256``), observation dimension, and optional robot profile.
    """
    errors: list[str] = list(validate_export_manifest_dict(manifest))

    weights = manifest.get("weights") or {}
    wname = weights.get("filename") if isinstance(weights, dict) else None
    if not isinstance(wname, str) or not wname:
        errors.append("manifest.weights.filename missing")
    elif not (package_root / wname).is_file():
        errors.append(f"weights file missing in package: {wname}")
    else:
        wpath = package_root / wname
        w_sha = weights.get("sha256") if isinstance(weights, dict) else None
        if isinstance(w_sha, str) and len(w_sha) == 64:
            got_w = sha256_file(wpath)
            if got_w != w_sha:
                errors.append(
                    f"weights.sha256 mismatch (manifest vs {wname})"
                )
        elif w_sha is not None:
            errors.append("manifest.weights.sha256 must be a 64-char hex string when present")
        elif not allow_missing_weights_sha256:
            errors.append(
                "manifest.weights.sha256 missing (re-pack with skill-foundry-package; "
                "or pass --allow-missing-weights-sha256 for legacy bundles only)"
            )

    mjcf = mjcf_path.expanduser().resolve()
    if not mjcf.is_file():
        errors.append(f"MJCF not found: {mjcf}")
    else:
        robot = manifest.get("robot") or {}
        want = robot.get("mjcf_sha256")
        if isinstance(want, str) and len(want) == 64:
            got = sha256_file(mjcf)
            if got != want:
                errors.append(
                    f"mjcf_sha256 mismatch (manifest {want[:12]}... vs local {got[:12]}...)"
                )

    prov = manifest.get("provenance") or {}
    ref_sha = prov.get("reference_sha256")
    if isinstance(ref_sha, str) and len(ref_sha) == 64:
        got_r = sha256_file(reference_path)
        if got_r != ref_sha:
            errors.append(
                f"reference_sha256 mismatch (manifest vs {reference_path})"
            )

    if expected_profile is not None:
        prof = (manifest.get("robot") or {}).get("profile")
        if prof != expected_profile:
            errors.append(
                f"robot.profile is {prof!r}, expected {expected_profile!r}"
            )

    obs = manifest.get("observation") or {}
    vd = obs.get("vector_dim")
    if isinstance(vd, int):
        imu = vd == rl_obs_dim(include_imu=True)
        base = vd == rl_obs_dim(include_imu=False)
        if not imu and not base:
            errors.append(
                f"observation.vector_dim {vd} does not match "
                f"rl_obs_dim(imu=False)={rl_obs_dim(include_imu=False)} or "
                f"rl_obs_dim(imu=True)={rl_obs_dim(include_imu=True)}"
            )

    act = manifest.get("action") or {}
    if act.get("dim") != 29:
        errors.append("manifest action.dim must be 29 for G1 29-DoF runtime MVP")

    return errors


def include_imu_from_manifest(manifest: dict[str, Any]) -> bool:
    vd = (manifest.get("observation") or {}).get("vector_dim")
    if not isinstance(vd, int):
        return False
    return vd == rl_obs_dim(include_imu=True)
