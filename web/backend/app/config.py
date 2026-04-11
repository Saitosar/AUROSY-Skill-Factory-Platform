"""Paths and settings for G1 Control web API."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_repo_root() -> Path:
    # web/backend/app/config.py -> parents: app, backend, web, repo
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="G1_", env_file=".env", extra="ignore")

    repo_root: Path = _default_repo_root()
    sdk_python_root: Path | None = None
    """Override: path to unitree_sdk2_python (default: <repo_root>/unitree_sdk2_python)."""

    skill_foundry_python_root: Path | None = None
    """Override: AUROSY Skill Foundry packages (default: <repo_root>/packages/skill_foundry)."""

    mjcf_path: Path | None = None
    """Default MJCF for skill-foundry-playback (e.g. unitree_mujoco/.../scene_29dof.xml)."""

    telemetry_mock_hz: float = 10.0
    use_dds_telemetry: bool = False
    """If True, attempt DDS lowstate (requires cyclonedds + robot/sim on host)."""

    joint_command_enabled: bool = True
    """When True, expose POST /api/joints/targets and merge holds into mock WebSocket telemetry."""

    dds_joint_bridge: bool = True
    """When True, publish ``rt/lowcmd`` from joint targets at ``dds_joint_publish_hz`` (MuJoCo / hardware)."""

    dds_joint_publish_hz: float = 100.0
    dds_domain_id: int = 1
    dds_interface: str = "lo0"
    """CycloneDDS interface (e.g. lo0 on Linux, en0 on macOS for loopback)."""

    @field_validator("dds_joint_bridge", mode="before")
    @classmethod
    def _parse_dds_joint_bridge(cls, v: object) -> bool:
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)

    @field_validator("joint_command_enabled", mode="before")
    @classmethod
    def _parse_joint_command_enabled(cls, v: object) -> bool:
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)

    # Phase 5 — platform (orchestrator + distribution)
    platform_data_dir: Path | None = None
    """SQLite DB, job workspaces, packages. Default: <web/backend>/data/platform."""

    job_timeout_sec: float = 7200.0
    max_concurrent_jobs_per_user: int = 1
    dev_user_id: str = "local-dev"
    """Used when X-User-Id header is absent (development only)."""

    platform_worker_enabled: bool = True
    """Set G1_PLATFORM_WORKER_ENABLED=0 to disable the background job worker loop."""

    skip_validation_gate: bool = False
    """If True, allow publishing packages without product validation (dev only). G1_SKIP_VALIDATION_GATE."""

    @field_validator("skip_validation_gate", mode="before")
    @classmethod
    def _parse_skip_validation_gate(cls, v: object) -> bool:
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)

    @field_validator("platform_worker_enabled", mode="before")
    @classmethod
    def _parse_platform_worker_enabled(cls, v: object) -> bool:
        if isinstance(v, str):
            return v.strip().lower() not in ("0", "false", "no", "off")
        return bool(v)

    def resolved_sdk_root(self) -> Path:
        if self.sdk_python_root is not None:
            return self.sdk_python_root.expanduser().resolve()
        return (self.repo_root / "unitree_sdk2_python").resolve()

    def resolved_skill_foundry_root(self) -> Path:
        if self.skill_foundry_python_root is not None:
            return self.skill_foundry_python_root.expanduser().resolve()
        return (self.repo_root / "packages" / "skill_foundry").resolve()

    def combined_pythonpath(self) -> str:
        """PYTHONPATH: Skill Foundry tree first, then Unitree Python SDK."""
        sf = str(self.resolved_skill_foundry_root().resolve())
        sdk = str(self.resolved_sdk_root().resolve())
        return os.pathsep.join((sf, sdk))

    def resolved_mjcf(self) -> Path | None:
        if self.mjcf_path is not None:
            p = self.mjcf_path.expanduser().resolve()
            return p if p.is_file() else None
        guess = self.repo_root / "unitree_mujoco" / "unitree_robots" / "g1" / "scene_29dof.xml"
        return guess.resolve() if guess.is_file() else None

    def resolved_platform_data_dir(self) -> Path:
        if self.platform_data_dir is not None:
            return self.platform_data_dir.expanduser().resolve()
        # web/backend/app/config.py -> parents[1] == web/backend
        return (Path(__file__).resolve().parents[1] / "data" / "platform").resolve()

    def platform_sqlite_path(self) -> Path:
        return self.resolved_platform_data_dir() / "platform.db"


def get_settings() -> Settings:
    return Settings()
