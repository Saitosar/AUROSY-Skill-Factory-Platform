"""Build export manifest.json from train config, reference trajectory, and train_run.json."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from skill_foundry_rl.obs_schema import RL_OBS_SCHEMA_REF, rl_obs_dim

DEFAULT_PACKAGE_VERSION = "1.0.0"
MANIFEST_SCHEMA_REF = "skill_foundry_export_manifest_v1"
DEFAULT_ROBOT_PROFILE = "unitree_g1_29dof"


def default_robot_profile() -> str:
    return DEFAULT_ROBOT_PROFILE


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_observation_blocks(*, include_imu: bool) -> tuple[list[dict[str, Any]], int]:
    """Observation vector layout matching :mod:`skill_foundry_rl.obs_schema` / ``G1TrackingEnv``."""
    blocks: list[dict[str, Any]] = [
        {"name": "motor_q", "offset": 0, "length": 29},
        {"name": "motor_dq", "offset": 29, "length": 29},
        {"name": "tracking_error", "offset": 58, "length": 29},
    ]
    if include_imu:
        from skill_foundry_rl.obs_schema import RL_OBS_DIM_BASE, RL_OBS_IMU_EXTRA_DIM

        blocks.append(
            {"name": "imu", "offset": RL_OBS_DIM_BASE, "length": RL_OBS_IMU_EXTRA_DIM}
        )
    dim = rl_obs_dim(include_imu=include_imu)
    return blocks, dim


def build_manifest(
    *,
    train_config: dict[str, Any],
    reference: dict[str, Any],
    train_run: dict[str, Any] | None = None,
    package_version: str = DEFAULT_PACKAGE_VERSION,
    robot_profile: str | None = None,
    train_config_path: Path | None = None,
) -> dict[str, Any]:
    """
    Assemble manifest dict (write JSON next to weights in the skill package).

    ``train_config`` is the same JSON used for ``skill-foundry-train``.
    ``reference`` is parsed ReferenceTrajectory v1 (e.g. from ``reference_trajectory.json``).
    ``train_run`` is optional; when present, ``mjcf_sha256`` / ``reference_sha256`` are checked for
    consistency with files on disk.
    """
    env_cfg = train_config.get("env") or {}
    mjcf_path = env_cfg.get("mjcf_path") or train_config.get("mjcf_path")
    if not mjcf_path:
        raise ValueError("train config must set env.mjcf_path")

    mjcf_resolved = Path(str(mjcf_path)).expanduser().resolve()
    if not mjcf_resolved.is_file():
        raise FileNotFoundError(f"MJCF not found: {mjcf_resolved}")

    mjcf_sha256 = _sha256_file(mjcf_resolved)
    if train_run is not None:
        tr_sha = train_run.get("mjcf_sha256")
        if isinstance(tr_sha, str) and tr_sha != mjcf_sha256:
            raise ValueError(
                f"train_run.json mjcf_sha256 ({tr_sha[:16]}...) does not match "
                f"current file {mjcf_resolved} ({mjcf_sha256[:16]}...). "
                "Use the same MJCF as training or refresh train_run."
            )

    include_imu = bool(env_cfg.get("include_imu_in_obs", False))
    blocks, vector_dim = build_observation_blocks(include_imu=include_imu)

    sim_dt = float(env_cfg.get("sim_dt", 0.005))
    delta_max = float(env_cfg.get("delta_max", 0.25))
    kp = float(env_cfg.get("kp", 150.0))
    kd = float(env_cfg.get("kd", 5.0))

    joint_order = reference.get("joint_order")
    if not isinstance(joint_order, list) or not joint_order:
        raise ValueError("reference must contain non-empty joint_order array")

    robot_model = reference.get("robot_model")
    if not isinstance(robot_model, str):
        robot_model = None

    profile = robot_profile or DEFAULT_ROBOT_PROFILE

    weights_name = "ppo_G1TrackingEnv.zip"

    prov: dict[str, Any] = {}
    if train_run is not None:
        rs = train_run.get("reference_sha256")
        if isinstance(rs, str):
            prov["reference_sha256"] = rs
        ph = train_run.get("phase")
        if isinstance(ph, str):
            prov["phase"] = ph
        tv = train_run.get("torch_version")
        if isinstance(tv, str):
            prov["torch_version"] = tv
        ck = train_run.get("checkpoint")
        if isinstance(ck, str):
            prov["train_run_checkpoint"] = ck

    if train_config_path is not None and train_config_path.is_file():
        prov["train_config_sha256"] = _sha256_file(train_config_path)

    manifest: dict[str, Any] = {
        "package_version": package_version,
        "manifest_schema_ref": MANIFEST_SCHEMA_REF,
        "observation": {
            "obs_schema_ref": RL_OBS_SCHEMA_REF,
            "vector_dim": vector_dim,
            "normalization": "none",
            "blocks": blocks,
        },
        "action": {
            "space": "box",
            "dim": 29,
            "low": -1.0,
            "high": 1.0,
            "residual_scale_rad": delta_max,
        },
        "control": {
            "dt_s": sim_dt,
            "kp": kp,
            "kd": kd,
        },
        "robot": {
            "profile": profile,
            "mjcf_sha256": mjcf_sha256,
            "mjcf_path": str(mjcf_resolved),
        },
        "joint_order": joint_order,
        "weights": {
            "format": "stable_baselines3_ppo_zip",
            "filename": weights_name,
        },
        "onnx": None,
    }
    if robot_model:
        manifest["robot"]["robot_model"] = robot_model
    if prov:
        manifest["provenance"] = prov

    return manifest


def manifest_json_bytes(manifest: dict[str, Any]) -> bytes:
    return json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
