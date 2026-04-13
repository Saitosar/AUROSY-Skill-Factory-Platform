"""Phase 6: persisted motion skill pipeline (capture → reference → train → eval → pack)."""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Literal

import numpy as np

from app.config import Settings
from app.platform_db import job_get
from app.platform_enqueue import EnqueueError, enqueue_train_job
from app.platform_paths import (
    motion_pipeline_dir,
    user_artifacts_dir,
    validate_artifact_name,
)
from app.platform_packaging import run_package_pack
from app.platform_packages import register_pack_output
from app.services.retargeting import parse_landmarks_payload, run_retargeting

try:
    from skill_foundry_phase0.contract_validator import validate_reference_trajectory_dict
except ImportError:
    validate_reference_trajectory_dict = None  # type: ignore[misc, assignment]

_PIPELINE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

MotionAction = Literal[
    "init",
    "attach_capture",
    "build_reference",
    "enqueue_train",
    "sync",
    "request_pack",
]


class MotionPipelineError(ValueError):
    """Invalid pipeline action or inconsistent state."""


def validate_pipeline_id(pipeline_id: str) -> str:
    t = pipeline_id.strip()
    if not _PIPELINE_ID_RE.match(t):
        raise MotionPipelineError(
            "pipeline_id must match ^[a-zA-Z0-9_-]{1,128}$",
        )
    return t


def _state_path(root: Path, user_id: str, pipeline_id: str) -> Path:
    d = motion_pipeline_dir(root, user_id, pipeline_id)
    return d / "state.json"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _now() -> float:
    return time.time()


def _empty_stage() -> dict[str, Any]:
    return {
        "status": "pending",
        "completed_at": None,
        "error": None,
    }


def _default_state(user_id: str, pipeline_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "pipeline_id": pipeline_id,
        "user_id": user_id,
        "updated_at": _now(),
        "stages": {
            "capture": {**_empty_stage()},
            "reference": {**_empty_stage()},
            "train": {**_empty_stage(), "job_id": None},
            "eval": {**_empty_stage()},
            "export": {**_empty_stage(), "package_id": None},
        },
        "capture_artifact": None,
        "landmarks_artifact": None,
    }


def load_state(root: Path, user_id: str, pipeline_id: str) -> dict[str, Any] | None:
    p = _state_path(root, user_id, pipeline_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_state(root: Path, user_id: str, pipeline_id: str, state: dict[str, Any]) -> None:
    state = dict(state)
    state["updated_at"] = _now()
    _atomic_write_json(_state_path(root, user_id, pipeline_id), state)


def _artifact_path(settings: Settings, user_id: str, name: str) -> Path:
    validate_artifact_name(name)
    root = settings.resolved_platform_data_dir()
    p = user_artifacts_dir(root, user_id) / name
    p = p.resolve()
    base = user_artifacts_dir(root, user_id).resolve()
    if not str(p).startswith(str(base)) or not p.is_file():
        raise MotionPipelineError(f"artifact not found: {name}")
    return p


def _reference_path_in_pipeline(settings: Settings, user_id: str, pipeline_id: str) -> Path:
    return motion_pipeline_dir(settings.resolved_platform_data_dir(), user_id, pipeline_id) / (
        "reference_trajectory.json"
    )


def _load_landmarks_array(artifact_path: Path) -> np.ndarray:
    raw_obj: Any = json.loads(artifact_path.read_text(encoding="utf-8"))
    if isinstance(raw_obj, dict):
        if "landmarks" in raw_obj:
            raw_obj = raw_obj["landmarks"]
        elif "frames" in raw_obj:
            raw_obj = raw_obj["frames"]
        else:
            raise MotionPipelineError("landmarks JSON must contain 'landmarks' or 'frames' array")
    arr = np.asarray(raw_obj, dtype=np.float32)
    return arr


def build_reference_trajectory_dict(
    *,
    joint_rows: list[list[float]],
    frequency_hz: float,
) -> dict[str, Any]:
    """ReferenceTrajectory v1 with full motor index order 0..28."""
    if frequency_hz <= 0:
        raise MotionPipelineError("frequency_hz must be positive")
    n = len(joint_rows)
    if n < 1:
        raise MotionPipelineError("joint_rows must be non-empty")
    if any(len(row) != 29 for row in joint_rows):
        raise MotionPipelineError("each joint row must have length 29 (G1 motor order)")

    dt = 1.0 / float(frequency_hz)
    vels: list[list[float]] = []
    for t in range(n):
        if t == 0 and n > 1:
            dq = [(joint_rows[1][i] - joint_rows[0][i]) / dt for i in range(29)]
        elif t == n - 1 and n > 1:
            dq = [(joint_rows[-1][i] - joint_rows[-2][i]) / dt for i in range(29)]
        elif n > 1:
            dq = [(joint_rows[t + 1][i] - joint_rows[t - 1][i]) / (2.0 * dt) for i in range(29)]
        else:
            dq = [0.0] * 29
        vels.append(dq)

    return {
        "schema_version": "1.0.0",
        "robot_model": "g1_29dof",
        "units": {"angle": "radians", "time": "seconds"},
        "frequency_hz": float(frequency_hz),
        "root_model": "root_not_in_reference",
        "joint_order": [str(i) for i in range(29)],
        "joint_positions": joint_rows,
        "joint_velocities": vels,
        "metadata": {"source": "motion_pipeline_retarget"},
    }


def _validate_reference_dict(ref: dict[str, Any]) -> None:
    if validate_reference_trajectory_dict is None:
        return
    errs = validate_reference_trajectory_dict(ref)
    if errs:
        raise MotionPipelineError("invalid reference_trajectory: " + "; ".join(errs))


def _refresh_job_derived_stages(settings: Settings, state: dict[str, Any]) -> dict[str, Any]:
    """Update train/eval stages from platform job + workspace files."""
    train = state["stages"]["train"]
    jid = train.get("job_id")
    if not isinstance(jid, str) or not jid:
        return state
    row = job_get(settings.platform_sqlite_path(), jid)
    if not row:
        train["status"] = "failed"
        train["error"] = "job not found"
        return state

    status = str(row["status"])
    root = settings.resolved_platform_data_dir()
    ws = root / str(row["workspace_relpath"])
    train_out = ws / "train_out"
    eval_path = train_out / "eval_motion.json"

    if status == "succeeded":
        train["status"] = "done"
        train["completed_at"] = train.get("completed_at") or float(row.get("finished_at") or _now())
        train["error"] = None
        ev = state["stages"]["eval"]
        if eval_path.is_file():
            ev["status"] = "done"
            ev["completed_at"] = ev.get("completed_at") or _now()
            ev["error"] = None
        elif str(row.get("mode")) == "amp":
            ev["status"] = "pending"
            ev["error"] = "eval_motion.json missing after AMP train"
        else:
            ev["status"] = "skipped"
            ev["error"] = None
    elif status == "failed":
        train["status"] = "failed"
        train["error"] = (row.get("error_message") or "job failed")[:2000]
        state["stages"]["eval"]["status"] = "pending"
    elif status in ("queued", "running"):
        train["status"] = status
        train["error"] = None
    else:
        train["status"] = "running"
        train["error"] = None
    return state


async def run_motion_pipeline_action(
    settings: Settings,
    user_id: str,
    *,
    pipeline_id: str,
    action: MotionAction,
    capture_artifact: str | None = None,
    landmarks_artifact: str | None = None,
    reference_artifact: str | None = None,
    frequency_hz: float = 50.0,
    force: bool = False,
    train_config: dict[str, Any] | None = None,
    train_mode: Literal["smoke", "train", "amp"] = "amp",
    demonstration_dataset: dict[str, Any] | None = None,
    demonstration_artifact: str | None = None,
    eval_only: bool = False,
    checkpoint_artifact: str | None = None,
    motion_export: dict[str, Any] | None = None,
    source_skeleton: str = "mediapipe_pose_33",
    target_robot: str = "unitree_g1_29dof",
    clip_to_limits: bool = True,
) -> dict[str, Any]:
    """
    Run one pipeline action. State is persisted under
    ``users/<user>/motion_pipelines/<pipeline_id>/state.json``.
    """
    pid = validate_pipeline_id(pipeline_id)
    root = settings.resolved_platform_data_dir()

    state = load_state(root, user_id, pid)
    if action == "init":
        state = _default_state(user_id, pid)
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state}

    if state is None:
        raise MotionPipelineError("unknown pipeline_id; call action=init first")

    if action == "attach_capture":
        if not capture_artifact:
            raise MotionPipelineError("attach_capture requires capture_artifact")
        _artifact_path(settings, user_id, capture_artifact)
        state["capture_artifact"] = capture_artifact
        cap = state["stages"]["capture"]
        cap["status"] = "done"
        cap["completed_at"] = _now()
        cap["error"] = None
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state}

    if action == "build_reference":
        ref_out = _reference_path_in_pipeline(settings, user_id, pid)
        if reference_artifact:
            src = _artifact_path(settings, user_id, reference_artifact)
            shutil.copy2(src, ref_out)
            ref = json.loads(ref_out.read_text(encoding="utf-8"))
        elif landmarks_artifact:
            src = _artifact_path(settings, user_id, landmarks_artifact)
            state["landmarks_artifact"] = landmarks_artifact
            arr = _load_landmarks_array(src)
            frames, _ = parse_landmarks_payload(arr)
            result = run_retargeting(
                sdk_root=settings.resolved_sdk_root(),
                skill_foundry_root=settings.resolved_skill_foundry_root(),
                frames=frames,
                source_skeleton=source_skeleton,
                target_robot=target_robot,
                clip_to_limits=clip_to_limits,
            )
            q = np.asarray(result.joint_angles_rad, dtype=np.float64)
            if q.ndim == 1:
                q = q.reshape(1, -1)
            if q.shape[1] != 29:
                raise MotionPipelineError(f"retarget produced {q.shape[1]} joints, expected 29")
            joint_rows = q.tolist()
            ref = build_reference_trajectory_dict(
                joint_rows=joint_rows,
                frequency_hz=frequency_hz,
            )
            ref_out.write_text(json.dumps(ref, indent=2), encoding="utf-8")
        else:
            raise MotionPipelineError(
                "build_reference requires reference_artifact or landmarks_artifact",
            )

        _validate_reference_dict(ref)
        rf = state["stages"]["reference"]
        rf["status"] = "done"
        rf["completed_at"] = _now()
        rf["error"] = None
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state}

    if action == "enqueue_train":
        if state["stages"]["reference"]["status"] != "done":
            raise MotionPipelineError("reference stage must be completed before enqueue_train")
        ref_path = _reference_path_in_pipeline(settings, user_id, pid)
        if not ref_path.is_file():
            raise MotionPipelineError("reference_trajectory.json missing in pipeline workspace")
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
        train = state["stages"]["train"]
        existing = train.get("job_id")
        if isinstance(existing, str) and existing and not force:
            row = job_get(settings.platform_sqlite_path(), existing)
            if row and str(row["status"]) in ("queued", "running", "succeeded"):
                state = _refresh_job_derived_stages(settings, state)
                save_state(root, user_id, pid, state)
                return {
                    "ok": True,
                    "pipeline_id": pid,
                    "state": state,
                    "job_id": existing,
                    "idempotent": True,
                }

        cfg = dict(train_config or {})
        try:
            jid = enqueue_train_job(
                settings,
                user_id,
                config=cfg,
                mode=train_mode,
                reference_trajectory=ref,
                reference_artifact=None,
                demonstration_dataset=demonstration_dataset,
                demonstration_artifact=demonstration_artifact,
                eval_only=eval_only,
                checkpoint_artifact=checkpoint_artifact,
                motion_export=motion_export,
            )
        except EnqueueError as e:
            raise MotionPipelineError(str(e)) from e

        train["job_id"] = jid
        train["status"] = "running"
        train["completed_at"] = None
        train["error"] = None
        state["stages"]["eval"] = {**_empty_stage()}
        state["stages"]["export"] = {**_empty_stage(), "package_id": None}
        state = _refresh_job_derived_stages(settings, state)
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state, "job_id": jid}

    if action == "sync":
        state = _refresh_job_derived_stages(settings, state)
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state}

    if action == "request_pack":
        state = _refresh_job_derived_stages(settings, state)
        train = state["stages"]["train"]
        jid = train.get("job_id")
        if not isinstance(jid, str) or not jid:
            raise MotionPipelineError("no train job to pack")
        row = job_get(settings.platform_sqlite_path(), jid)
        if not row or str(row["status"]) != "succeeded":
            raise MotionPipelineError("train job must succeed before request_pack")
        ex = state["stages"]["export"]
        if isinstance(ex.get("package_id"), str) and ex["package_id"] and not force:
            save_state(root, user_id, pid, state)
            return {
                "ok": True,
                "pipeline_id": pid,
                "state": state,
                "package_id": ex["package_id"],
                "idempotent": True,
            }

        ws = root / str(row["workspace_relpath"])
        train_out = ws / "train_out"
        cfg = ws / "train_config.json"
        ref = ws / "reference_trajectory.json"
        if not train_out.is_dir() or not cfg.is_file() or not ref.is_file():
            raise MotionPipelineError("job workspace missing train_out, config, or reference")
        tmp_out = ws / f"pack_{jid}.tar.gz"
        result = await run_package_pack(
            settings.resolved_sdk_root(),
            settings.resolved_skill_foundry_root(),
            train_config=cfg,
            reference_trajectory=ref,
            run_dir=train_out,
            output_archive=tmp_out,
        )
        if int(result.get("exit_code") or 1) != 0:
            raise MotionPipelineError(
                result.get("stderr") or "skill-foundry-package failed",
            )
        pkg_id = register_pack_output(
            settings,
            user_id,
            archive_path=tmp_out,
            label=None,
            train_output_dir=train_out,
        )
        ex["status"] = "done"
        ex["completed_at"] = _now()
        ex["package_id"] = pkg_id
        ex["error"] = None
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state, "package_id": pkg_id}

    raise MotionPipelineError(f"unknown action: {action}")


def get_motion_pipeline_state(settings: Settings, user_id: str, pipeline_id: str) -> dict[str, Any]:
    pid = validate_pipeline_id(pipeline_id)
    root = settings.resolved_platform_data_dir()
    state = load_state(root, user_id, pid)
    if state is None:
        raise MotionPipelineError("unknown pipeline_id")
    state = _refresh_job_derived_stages(settings, state)
    save_state(root, user_id, pid, state)
    return {"ok": True, "pipeline_id": pid, "state": state}
