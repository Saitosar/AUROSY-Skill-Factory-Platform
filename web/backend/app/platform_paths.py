"""Filesystem layout under G1_PLATFORM_DATA_DIR."""

from __future__ import annotations

import re
from pathlib import Path

_ARTIFACT_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,255}$")
_POSE_DRAFT_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,200}$")


def sanitize_user_id(raw: str) -> str:
    s = raw.strip()
    if not s or len(s) > 128:
        raise ValueError("invalid user id")
    if not re.match(r"^[a-zA-Z0-9_-]+$", s):
        raise ValueError("user id must match [a-zA-Z0-9_-]+")
    return s


def validate_artifact_name(name: str) -> str:
    if not _ARTIFACT_NAME_RE.match(name):
        raise ValueError("artifact name must match ^[a-zA-Z0-9_.-]+$")
    return name


def validate_pose_draft_name(name: str) -> str:
    t = name.strip()
    if not _POSE_DRAFT_NAME_RE.match(t):
        raise ValueError("pose draft name must match ^[a-zA-Z0-9_.-]{1,200}$")
    return t


def user_root(platform_root: Path, user_id: str) -> Path:
    return platform_root / "users" / user_id


def user_artifacts_dir(platform_root: Path, user_id: str) -> Path:
    return user_root(platform_root, user_id) / "artifacts"


def user_jobs_dir(platform_root: Path, user_id: str) -> Path:
    return user_root(platform_root, user_id) / "jobs"


def user_packages_dir(platform_root: Path, user_id: str) -> Path:
    return user_root(platform_root, user_id) / "packages"


def user_pose_drafts_dir(platform_root: Path, user_id: str) -> Path:
    p = user_root(platform_root, user_id) / "pose_drafts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def job_workspace(platform_root: Path, user_id: str, job_id: str) -> Path:
    return user_jobs_dir(platform_root, user_id) / job_id


def workspace_relpath(user_id: str, job_id: str) -> str:
    return f"users/{user_id}/jobs/{job_id}"


def bundle_relpath(user_id: str, filename: str) -> str:
    return f"users/{user_id}/packages/{filename}"
