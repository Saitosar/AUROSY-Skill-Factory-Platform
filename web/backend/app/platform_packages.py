"""Register and resolve skill bundles for Phase 5 distribution."""

from __future__ import annotations

import json
import shutil
import tarfile
import uuid
from pathlib import Path
from typing import Any

from app.config import Settings
from app.platform_db import package_get, package_insert
from app.platform_paths import bundle_relpath, user_packages_dir


def _try_manifest_summary_from_tarball(path: Path) -> str | None:
    try:
        with tarfile.open(path, "r:*") as tf:
            for m in tf.getmembers():
                if m.name.endswith("manifest.json") and m.isfile():
                    f = tf.extractfile(m)
                    if f is None:
                        return None
                    data = json.loads(f.read().decode("utf-8"))
                    return json.dumps(
                        {
                            "package_version": data.get("package_version"),
                            "robot": data.get("robot"),
                        },
                        indent=2,
                    )
    except (OSError, json.JSONDecodeError, tarfile.TarError):
        return None
    return None


def validation_state_from_report_file(path: Path) -> tuple[int | None, str | None]:
    """Map ``validation_report.json`` to (validation_passed, validation_summary) for SQLite."""
    if not path.is_file():
        return None, None
    try:
        rep: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    if rep.get("applicable") is False:
        summary = json.dumps({"applicable": False})
        return None, summary
    passed = rep.get("passed")
    if passed is True:
        vp = 1
    elif passed is False:
        vp = 0
    else:
        vp = None
    summary = json.dumps(
        {
            "passed": rep.get("passed"),
            "metrics": rep.get("metrics"),
            "failure_reasons": rep.get("failure_reasons"),
            "error": rep.get("error"),
        },
        indent=2,
    )
    return vp, summary


def validation_state_from_tarball(path: Path) -> tuple[int | None, str | None]:
    """Read ``product_validation`` from bundled ``manifest.json`` if present."""
    try:
        with tarfile.open(path, "r:*") as tf:
            manifest_data: dict[str, Any] | None = None
            for m in tf.getmembers():
                if m.name.endswith("manifest.json") and m.isfile():
                    f = tf.extractfile(m)
                    if f is None:
                        break
                    raw = json.loads(f.read().decode("utf-8"))
                    if isinstance(raw, dict):
                        manifest_data = raw
                    break
        if not manifest_data:
            return None, None
        pv = manifest_data.get("product_validation")
        if not isinstance(pv, dict):
            return None, None
        if pv.get("applicable") is False:
            return None, json.dumps({"applicable": False, "source": "manifest"})
        passed = pv.get("passed")
        if passed is True:
            vp = 1
        elif passed is False:
            vp = 0
        else:
            vp = None
        summary = json.dumps(
            {"passed": passed, "metrics": pv.get("metrics"), "source": "manifest"},
            indent=2,
        )
        return vp, summary
    except (OSError, json.JSONDecodeError, tarfile.TarError):
        return None, None


def register_uploaded_tarball(
    settings: Settings,
    user_id: str,
    *,
    src_path: Path,
    label: str | None,
) -> str:
    pkg_id = str(uuid.uuid4())
    root = settings.resolved_platform_data_dir()
    dest_dir = user_packages_dir(root, user_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{pkg_id}.tar.gz"
    shutil.copy2(src_path, dest)
    rel = bundle_relpath(user_id, f"{pkg_id}.tar.gz")
    summary = _try_manifest_summary_from_tarball(dest)
    vp, vsum = validation_state_from_tarball(dest)
    package_insert(
        settings.platform_sqlite_path(),
        package_id=pkg_id,
        user_id=user_id,
        label=label,
        published=False,
        bundle_relpath=rel,
        manifest_summary=summary,
        validation_passed=vp,
        validation_summary=vsum,
    )
    return pkg_id


def register_pack_output(
    settings: Settings,
    user_id: str,
    *,
    archive_path: Path,
    label: str | None,
    train_output_dir: Path | None = None,
) -> str:
    """Move pack output into user packages dir and insert DB row."""
    pkg_id = str(uuid.uuid4())
    root = settings.resolved_platform_data_dir()
    dest_dir = user_packages_dir(root, user_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{pkg_id}.tar.gz"
    shutil.move(str(archive_path), str(dest))
    rel = bundle_relpath(user_id, f"{pkg_id}.tar.gz")
    summary = _try_manifest_summary_from_tarball(dest)
    vp: int | None = None
    vsum: str | None = None
    if train_output_dir is not None:
        vp, vsum = validation_state_from_report_file(train_output_dir / "validation_report.json")
    if vp is None and vsum is None:
        vp, vsum = validation_state_from_tarball(dest)
    package_insert(
        settings.platform_sqlite_path(),
        package_id=pkg_id,
        user_id=user_id,
        label=label,
        published=False,
        bundle_relpath=rel,
        manifest_summary=summary,
        validation_passed=vp,
        validation_summary=vsum,
    )
    return pkg_id


def bundle_absolute_path(settings: Settings, bundle_relpath: str) -> Path:
    return settings.resolved_platform_data_dir() / bundle_relpath


def can_download_package(settings: Settings, row: dict, caller_user_id: str) -> bool:
    if row["user_id"] == caller_user_id:
        return True
    return bool(row.get("published"))
