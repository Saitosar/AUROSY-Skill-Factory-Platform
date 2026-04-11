"""Resolve paths to vendored isri-aist/g1_description and default MJCF."""

from __future__ import annotations

from pathlib import Path


def skill_foundry_validation_root() -> Path:
    return Path(__file__).resolve().parent


def default_g1_description_dir() -> Path:
    """Directory containing ``urdf/``, ``meshes/`` (isri-aist/g1_description layout)."""
    return skill_foundry_validation_root() / "models" / "g1_description"


def default_g1_urdf_path() -> Path:
    return default_g1_description_dir() / "urdf" / "g1_29dof.urdf"


def default_package_dir_for_urdf() -> Path:
    """Parent of ``g1_description/`` for resolving ``package://g1_description/...`` in URDF."""
    return default_g1_description_dir().parent
