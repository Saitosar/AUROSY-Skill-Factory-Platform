"""Build DemonstrationDataset v1 JSON from a headless playback log."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from skill_foundry_phase0.contract_validator import validate_demonstration_dataset_dict
from skill_foundry_sim.headless_playback import PlaybackLog

# obs = concat(motor_q[29], motor_dq[29]); act = ctrl[29]; optional ref = reference joint q[29]
OBS_SCHEMA_REF = "skill_foundry_sim_motor_q_dq_ctrl_v1"


def find_git_root(start: Path) -> Path | None:
    """Walk parents from ``start`` until a directory containing `.git` is found."""
    cur = start.resolve()
    for _ in range(64):
        if (cur / ".git").is_dir():
            return cur
        parent = cur.parent
        if parent == cur:
            return None
        cur = parent
    return None


def try_git_commit(repo_root: Path | None = None) -> str | None:
    """Resolve git HEAD like preprocess CLI: env GIT_COMMIT / SOURCE_GIT_COMMIT, else git rev-parse."""
    env = os.environ.get("GIT_COMMIT") or os.environ.get("SOURCE_GIT_COMMIT")
    if env:
        return env.strip() or None
    cwd = repo_root if repo_root is not None and repo_root.is_dir() else None
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def build_demonstration_dataset(
    log: PlaybackLog,
    *,
    robot_model: str = "g1_29dof",
    sim_dt: float,
    seed: int,
    mujoco_version: str | None = None,
    simulator_commit: str | None = None,
    repo_root_for_git: Path | None = None,
    episode_id: str = "ep_0001",
    include_ref: bool = True,
) -> dict[str, Any]:
    """
    Assemble DemonstrationDataset v1: one episode, one step per simulation step.

    obs: 58 floats — motor joint positions then velocities (G1 29+29, motor index order).
    act: 29 floats — torque commands from MuJoCo ctrl.
    """
    n = int(log.motor_q.shape[0])
    sampling_hz = float(1.0 / sim_dt)
    if mujoco_version is None:
        mujoco_version = str(log.meta.get("mujoco_version", "unknown"))
    simulator = f"mujoco {mujoco_version}"

    if simulator_commit is None:
        simulator_commit = try_git_commit(repo_root_for_git)

    steps: list[dict[str, Any]] = []
    for k in range(n):
        obs = np.concatenate([log.motor_q[k], log.motor_dq[k]], axis=0)
        step: dict[str, Any] = {
            "obs": obs.tolist(),
            "act": log.ctrl[k].tolist(),
            "done": k == n - 1,
        }
        if include_ref:
            step["ref"] = log.reference_motor_q[k].tolist()
        steps.append(step)

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "robot_model": robot_model,
        "sampling_hz": sampling_hz,
        "obs_schema_ref": OBS_SCHEMA_REF,
        "seed": int(seed),
        "simulator": simulator,
        "episodes": [{"episode_id": episode_id, "steps": steps}],
    }
    if simulator_commit:
        payload["simulator_commit"] = simulator_commit

    errs = validate_demonstration_dataset_dict(payload)
    if errs:
        raise ValueError("invalid demonstration dataset: " + "; ".join(errs))

    return payload


def write_demonstration_dataset_json(path: Path | str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
