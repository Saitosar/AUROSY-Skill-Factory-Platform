"""Assemble skill package archive: manifest + checkpoint + optional policy .pt / ONNX."""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from skill_foundry_export.manifest import (
    DEFAULT_PACKAGE_VERSION,
    build_manifest,
    manifest_json_bytes,
)

# Bundled ReferenceTrajectory v1 for Robot runtime (Phase 4.2).
REFERENCE_BUNDLE_FILENAME = "reference_trajectory.json"
# Phase 6.1 product validation report (optional).
VALIDATION_REPORT_FILENAME = "validation_report.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def package_skill(
    *,
    train_config: dict[str, Any],
    reference_path: Path,
    run_dir: Path,
    output_archive: Path,
    train_config_path: Path | None = None,
    package_version: str | None = None,
    robot_profile: str | None = None,
    include_policy_pt: bool = False,
    include_onnx: bool = False,
    onnx_opset: int = 17,
) -> dict[str, Any]:
    """
    Create a ``.tar.gz`` containing ``manifest.json``, ``reference_trajectory.json`` (same file
    as training), ``ppo_G1TrackingEnv.zip``, and optional ``policy_weights.pt`` / ``policy.onnx``.

    ``run_dir`` must contain ``train_run.json`` and the SB3 checkpoint zip (default stem
    ``ppo_G1TrackingEnv.zip``).
    """
    reference_path = reference_path.expanduser().resolve()
    run_dir = run_dir.expanduser().resolve()
    output_archive = output_archive.expanduser().resolve()
    output_archive.parent.mkdir(parents=True, exist_ok=True)

    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    ref_sha = _sha256_file(reference_path)

    train_run_path = run_dir / "train_run.json"
    if not train_run_path.is_file():
        raise FileNotFoundError(f"train_run.json not found under {run_dir}")

    train_run = json.loads(train_run_path.read_text(encoding="utf-8"))
    tr_ref = train_run.get("reference_sha256")
    if isinstance(tr_ref, str) and tr_ref != ref_sha:
        raise ValueError(
            f"reference file sha256 does not match train_run.json ({reference_path})"
        )

    ckpt_name = "ppo_G1TrackingEnv.zip"
    ckpt_path = run_dir / ckpt_name
    if not ckpt_path.is_file():
        alt = train_run.get("checkpoint")
        if isinstance(alt, str):
            alt_path = Path(alt)
            if alt_path.is_file():
                ckpt_path = alt_path
                ckpt_name = alt_path.name
            elif (run_dir / alt_path.name).is_file():
                ckpt_path = run_dir / alt_path.name
                ckpt_name = alt_path.name
        if not ckpt_path.is_file():
            raise FileNotFoundError(
                f"PPO checkpoint not found: expected {run_dir / 'ppo_G1TrackingEnv.zip'}"
            )

    pv = package_version or DEFAULT_PACKAGE_VERSION
    manifest = build_manifest(
        train_config=train_config,
        reference=reference,
        train_run=train_run,
        package_version=pv,
        robot_profile=robot_profile,
        train_config_path=train_config_path,
    )
    manifest["weights"]["filename"] = ckpt_name
    manifest["weights"]["sha256"] = _sha256_file(ckpt_path)
    manifest["reference_trajectory"] = {
        "filename": REFERENCE_BUNDLE_FILENAME,
        "schema_ref": "reference_trajectory_v1",
    }

    validation_path = run_dir / VALIDATION_REPORT_FILENAME
    if validation_path.is_file():
        val_raw = json.loads(validation_path.read_text(encoding="utf-8"))
        manifest["product_validation"] = {
            "filename": VALIDATION_REPORT_FILENAME,
            "validation_report_schema_ref": val_raw.get("validation_report_schema_ref"),
            "applicable": val_raw.get("applicable", True),
            "passed": val_raw.get("passed"),
            "metrics": val_raw.get("metrics"),
        }

    summary: dict[str, Any] = {
        "manifest": manifest,
        "archive": str(output_archive),
        "files": [ckpt_name, "manifest.json", REFERENCE_BUNDLE_FILENAME],
    }
    if validation_path.is_file():
        summary["files"].append(VALIDATION_REPORT_FILENAME)

    policy_pt_name = "policy_weights.pt"
    onnx_name = "policy.onnx"

    with tempfile.TemporaryDirectory(prefix="skill_foundry_pkg_") as tmp:
        root = Path(tmp)
        man_path = root / "manifest.json"
        man_path.write_bytes(manifest_json_bytes(manifest))
        shutil.copy2(ckpt_path, root / ckpt_name)
        shutil.copy2(reference_path, root / REFERENCE_BUNDLE_FILENAME)
        if validation_path.is_file():
            shutil.copy2(validation_path, root / VALIDATION_REPORT_FILENAME)

        if include_policy_pt:
            from skill_foundry_export.policy_checkpoint import export_policy_state_dict

            pt_path = root / policy_pt_name
            export_policy_state_dict(ckpt_path, pt_path)
            manifest["policy_weights_pt"] = {
                "filename": policy_pt_name,
                "description": "Torch state_dict of SB3 ActorCriticPolicy (policy.* keys).",
            }
            man_path.write_bytes(manifest_json_bytes(manifest))
            summary["files"].append(policy_pt_name)

        if include_onnx:
            from skill_foundry_export.onnx_export import export_ppo_policy_onnx

            onnx_path = root / onnx_name
            meta = export_ppo_policy_onnx(
                ckpt_path,
                onnx_path,
                obs_dim=int(manifest["observation"]["vector_dim"]),
                opset=onnx_opset,
            )
            manifest["onnx"] = {
                "filename": onnx_name,
                "opset": onnx_opset,
                **meta,
            }
            man_path.write_bytes(manifest_json_bytes(manifest))
            summary["files"].append(onnx_name)

        if output_archive.suffix == ".zip":
            raise ValueError("use .tar.gz for Phase 4.1 MVP (zip support can be added later)")

        with tarfile.open(output_archive, "w:gz") as tf:
            for p in sorted(root.iterdir()):
                tf.add(p, arcname=p.name)

    summary["files"] = sorted(set(summary["files"]))
    return summary
