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
from app.platform_enqueue import EnqueueError, enqueue_train_job, enqueue_video_process_job
from app.platform_paths import (
    motion_pipeline_dir,
    user_artifacts_dir,
    validate_artifact_name,
)
from app.platform_packaging import run_package_pack
from app.platform_packages import register_pack_output
from app.services.retargeting import parse_landmarks_payload, run_retargeting

try:
    from skill_foundry_retarget.bvh_to_trajectory import BVHToTrajectoryConverter
except ImportError:
    BVHToTrajectoryConverter = None  # type: ignore[assignment,misc]

try:
    from skill_foundry_phase0.contract_validator import validate_reference_trajectory_dict
except ImportError:
    validate_reference_trajectory_dict = None  # type: ignore[misc, assignment]

try:
    from skill_foundry_validation.pretraining_validator import (
        PreTrainingConfig,
        validate_pretraining,
    )
except ImportError:
    PreTrainingConfig = None  # type: ignore[misc, assignment]
    validate_pretraining = None  # type: ignore[misc, assignment]

try:
    from skill_foundry_validation.publishing_gate import (
        PublishingCriteria,
        evaluate_publishing_gate_from_paths,
    )
except ImportError:
    PublishingCriteria = None  # type: ignore[misc, assignment]
    evaluate_publishing_gate_from_paths = None  # type: ignore[misc, assignment]

try:
    from skill_foundry_preprocess import preprocess_landmarks_payload
except ImportError:
    preprocess_landmarks_payload = None  # type: ignore[misc, assignment]

_PIPELINE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

MotionAction = Literal[
    "init",
    "attach_capture",
    "attach_video",
    "extract_poses",
    "preprocess_motion",
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
        "schema_version": "1.1",
        "pipeline_id": pipeline_id,
        "user_id": user_id,
        "updated_at": _now(),
        "stages": {
            "video_ingest": {**_empty_stage(), "video_id": None},
            "pose_extract": {**_empty_stage(), "job_id": None},
            "preprocess": {**_empty_stage()},
            "capture": {**_empty_stage()},
            "reference": {**_empty_stage()},
            "train": {**_empty_stage(), "job_id": None},
            "eval": {**_empty_stage()},
            "export": {**_empty_stage(), "package_id": None},
        },
        "video_artifact": None,
        "capture_artifact": None,
        "landmarks_artifact": None,
        "preprocessed_artifact": None,
        "source_type": None,
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


def _resolve_artifact_path(settings: Settings, user_id: str, name: str) -> Path:
    """Resolve user artifact name or platform-data relative artifact path."""
    try:
        return _artifact_path(settings, user_id, name)
    except MotionPipelineError:
        root = settings.resolved_platform_data_dir().resolve()
        p = (root / name).resolve()
        if not str(p).startswith(str(root)) or not p.is_file():
            raise MotionPipelineError(f"artifact not found: {name}")
        return p


def _reference_path_in_pipeline(settings: Settings, user_id: str, pipeline_id: str) -> Path:
    return motion_pipeline_dir(settings.resolved_platform_data_dir(), user_id, pipeline_id) / (
        "reference_trajectory.json"
    )


def _preprocessed_path_in_pipeline(settings: Settings, user_id: str, pipeline_id: str) -> Path:
    return motion_pipeline_dir(settings.resolved_platform_data_dir(), user_id, pipeline_id) / (
        "preprocessed_landmarks.json"
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


def _load_capture_landmarks_array(
    artifact_path: Path,
    *,
    fallback_frequency_hz: float,
) -> tuple[np.ndarray, float]:
    suffix = artifact_path.suffix.lower()
    if suffix != ".bvh":
        return _load_landmarks_array(artifact_path), fallback_frequency_hz

    if BVHToTrajectoryConverter is None:
        raise MotionPipelineError("BVH converter is unavailable: install skill_foundry_retarget")
    converter = BVHToTrajectoryConverter()
    try:
        motion = converter.parse(artifact_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise MotionPipelineError(f"invalid BVH artifact: {exc}") from exc
    hz = fallback_frequency_hz
    if motion.frame_time > 0:
        hz = 1.0 / motion.frame_time
    return converter.to_landmarks_approx(motion), hz


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


def _run_pretraining_validation(ref: dict[str, Any]) -> dict[str, Any]:
    """Run pre-training validation and return result dict."""
    if validate_pretraining is None:
        return {"skipped": True, "reason": "pretraining_validator not available"}

    try:
        result = validate_pretraining(ref)
        return result.to_dict()
    except Exception as e:
        return {"skipped": True, "reason": f"validation error: {e}"}


def _run_landmark_preprocess(
    raw_path: Path,
    out_path: Path,
    *,
    filter_type: Literal["savgol", "kalman", "both"],
    window_length: int,
    polyorder: int,
    confidence_threshold: float,
    process_noise: float,
    measurement_noise: float,
) -> dict[str, Any]:
    if preprocess_landmarks_payload is None:
        raise MotionPipelineError(
            "landmark preprocessing is unavailable: install skill_foundry_preprocess",
        )
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    preprocessed = preprocess_landmarks_payload(
        payload,
        filter_type=filter_type,
        window_length=window_length,
        polyorder=polyorder,
        confidence_threshold=confidence_threshold,
        process_noise=process_noise,
        measurement_noise=measurement_noise,
    )
    preprocessed.save_json(out_path)
    return {
        "source_format": preprocessed.source_format,
        "preprocessing_config": preprocessed.preprocessing_config,
        "quality_metrics": preprocessed.quality_metrics,
        "frame_count": int(preprocessed.landmarks.shape[0]),
    }


def _refresh_video_process_stage(settings: Settings, state: dict[str, Any]) -> dict[str, Any]:
    """Update pose_extract stage from video process job."""
    pe = state["stages"].get("pose_extract", {})
    jid = pe.get("job_id")
    if not isinstance(jid, str) or not jid:
        return state

    row = job_get(settings.platform_sqlite_path(), jid)
    if not row:
        pe["status"] = "failed"
        pe["error"] = "job not found"
        return state

    status = str(row["status"])
    root = settings.resolved_platform_data_dir()
    ws = root / str(row["workspace_relpath"])
    result_path = ws / "process_result.json"
    landmarks_path = ws / "landmarks.json"

    if status == "succeeded":
        pe["status"] = "done"
        pe["completed_at"] = pe.get("completed_at") or float(row.get("finished_at") or _now())
        pe["error"] = None

        if result_path.is_file():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                pe["frame_count"] = result.get("frame_count")
                pe["valid_frame_count"] = result.get("valid_frame_count")
                pe["confidence_mean"] = result.get("confidence_mean")

                if landmarks_path.is_file():
                    state["landmarks_artifact"] = str(landmarks_path.relative_to(root))
                    cap = state["stages"]["capture"]
                    cap["status"] = "done"
                    cap["completed_at"] = _now()
            except (json.JSONDecodeError, OSError):
                pass

    elif status == "failed":
        pe["status"] = "failed"
        pe["error"] = (row.get("error_message") or "job failed")[:2000]
    elif status in ("queued", "running"):
        pe["status"] = status
        pe["error"] = None
    else:
        pe["status"] = "running"
        pe["error"] = None

    return state


def _refresh_job_derived_stages(settings: Settings, state: dict[str, Any]) -> dict[str, Any]:
    """Update train/eval stages from platform job + workspace files."""
    state = _refresh_video_process_stage(settings, state)
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
    bvh_artifact: str | None = None,
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
    preprocess_filter: Literal["savgol", "kalman", "both"] = "both",
    preprocess_window_length: int = 7,
    preprocess_polyorder: int = 2,
    preprocess_confidence_threshold: float = 0.3,
    preprocess_process_noise: float = 0.01,
    preprocess_measurement_noise: float = 0.1,
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
        state["source_type"] = "capture"
        cap = state["stages"]["capture"]
        cap["status"] = "done"
        cap["completed_at"] = _now()
        cap["error"] = None
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state}

    if action == "attach_video":
        video_id = capture_artifact
        if not video_id:
            raise MotionPipelineError("attach_video requires video_id in capture_artifact")

        from app.services.video_ingest import get_video_metadata, get_video_file_path

        meta = get_video_metadata(settings, user_id, video_id)
        if meta is None:
            raise MotionPipelineError(f"video not found: {video_id}")

        video_path = get_video_file_path(settings, user_id, video_id)
        if video_path is None:
            raise MotionPipelineError(f"video file not found for {video_id}")

        state["video_artifact"] = meta.get("file_path")
        state["source_type"] = "video"
        vi = state["stages"]["video_ingest"]
        vi["status"] = "done"
        vi["video_id"] = video_id
        vi["completed_at"] = _now()
        vi["error"] = None
        vi["metadata"] = {
            "title": meta.get("title"),
            "duration_sec": meta.get("duration_sec"),
            "fps": meta.get("fps"),
            "source_url": meta.get("source_url"),
        }
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state}

    if action == "extract_poses":
        vi = state["stages"]["video_ingest"]
        if vi["status"] != "done":
            raise MotionPipelineError("video_ingest stage must be completed before extract_poses")

        video_id = vi.get("video_id")
        video_artifact = state.get("video_artifact")
        if not video_id or not video_artifact:
            raise MotionPipelineError("no video attached to pipeline")

        pe = state["stages"]["pose_extract"]
        existing_job = pe.get("job_id")

        if isinstance(existing_job, str) and existing_job and not force:
            row = job_get(settings.platform_sqlite_path(), existing_job)
            if row and str(row["status"]) in ("queued", "running", "succeeded"):
                state = _refresh_video_process_stage(settings, state)
                save_state(root, user_id, pid, state)
                return {
                    "ok": True,
                    "pipeline_id": pid,
                    "state": state,
                    "job_id": existing_job,
                    "idempotent": True,
                }

        try:
            jid = enqueue_video_process_job(
                settings,
                user_id,
                video_id=video_id,
                video_artifact=video_artifact,
                target_fps=frequency_hz,
            )
        except EnqueueError as e:
            raise MotionPipelineError(str(e)) from e

        pe["job_id"] = jid
        pe["status"] = "running"
        pe["completed_at"] = None
        pe["error"] = None
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state, "job_id": jid}

    if action == "preprocess_motion":
        pe = state["stages"]["pose_extract"]
        if pe["status"] != "done":
            raise MotionPipelineError("pose_extract stage must be completed before preprocess_motion")

        prep_stage = state["stages"]["preprocess"]
        if prep_stage.get("status") == "done" and not force:
            save_state(root, user_id, pid, state)
            return {"ok": True, "pipeline_id": pid, "state": state, "idempotent": True}

        source_name = (
            landmarks_artifact
            or state.get("landmarks_artifact")
            or state.get("capture_artifact")
        )
        if not isinstance(source_name, str) or not source_name:
            raise MotionPipelineError("preprocess_motion requires landmarks_artifact or capture_artifact")
        src = _resolve_artifact_path(settings, user_id, source_name)
        out_path = _preprocessed_path_in_pipeline(settings, user_id, pid)
        summary = _run_landmark_preprocess(
            src,
            out_path,
            filter_type=preprocess_filter,
            window_length=preprocess_window_length,
            polyorder=preprocess_polyorder,
            confidence_threshold=preprocess_confidence_threshold,
            process_noise=preprocess_process_noise,
            measurement_noise=preprocess_measurement_noise,
        )
        state["preprocessed_artifact"] = str(out_path.relative_to(root))
        prep_stage["status"] = "done"
        prep_stage["completed_at"] = _now()
        prep_stage["error"] = None
        prep_stage["summary"] = summary
        save_state(root, user_id, pid, state)
        return {"ok": True, "pipeline_id": pid, "state": state, "preprocess": summary}

    if action == "build_reference":
        ref_out = _reference_path_in_pipeline(settings, user_id, pid)
        if reference_artifact:
            src = _resolve_artifact_path(settings, user_id, reference_artifact)
            shutil.copy2(src, ref_out)
            ref = json.loads(ref_out.read_text(encoding="utf-8"))
        elif landmarks_artifact or capture_artifact or bvh_artifact:
            capture_name = landmarks_artifact or capture_artifact or bvh_artifact
            if capture_name is None:
                raise MotionPipelineError("capture artifact is required")
            src = _resolve_artifact_path(settings, user_id, capture_name)
            if landmarks_artifact:
                state["landmarks_artifact"] = landmarks_artifact
            if capture_artifact:
                state["capture_artifact"] = capture_artifact
            if bvh_artifact:
                state["capture_artifact"] = bvh_artifact

            prep_stage = state["stages"]["preprocess"]
            if bvh_artifact is None:
                prep_out = _preprocessed_path_in_pipeline(settings, user_id, pid)
                auto_summary = _run_landmark_preprocess(
                    src,
                    prep_out,
                    filter_type=preprocess_filter,
                    window_length=preprocess_window_length,
                    polyorder=preprocess_polyorder,
                    confidence_threshold=preprocess_confidence_threshold,
                    process_noise=preprocess_process_noise,
                    measurement_noise=preprocess_measurement_noise,
                )
                src = prep_out
                state["preprocessed_artifact"] = str(prep_out.relative_to(root))
                prep_stage["status"] = "done"
                prep_stage["completed_at"] = _now()
                prep_stage["error"] = None
                prep_stage["summary"] = auto_summary

            arr, effective_frequency_hz = _load_capture_landmarks_array(
                src,
                fallback_frequency_hz=frequency_hz,
            )
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
                frequency_hz=effective_frequency_hz,
            )
            ref_out.write_text(json.dumps(ref, indent=2), encoding="utf-8")
        else:
            preprocessed_name = state.get("preprocessed_artifact")
            if not isinstance(preprocessed_name, str) or not preprocessed_name:
                raise MotionPipelineError(
                    "build_reference requires reference_artifact, landmarks_artifact, capture_artifact, or bvh_artifact",
                )
            src = _resolve_artifact_path(settings, user_id, preprocessed_name)
            arr, effective_frequency_hz = _load_capture_landmarks_array(
                src,
                fallback_frequency_hz=frequency_hz,
            )
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
                frequency_hz=effective_frequency_hz,
            )
            ref_out.write_text(json.dumps(ref, indent=2), encoding="utf-8")

        _validate_reference_dict(ref)

        pretraining_validation = _run_pretraining_validation(ref)
        rf = state["stages"]["reference"]
        rf["status"] = "done"
        rf["completed_at"] = _now()
        rf["error"] = None
        rf["pretraining_validation"] = pretraining_validation
        save_state(root, user_id, pid, state)

        result = {"ok": True, "pipeline_id": pid, "state": state}
        if pretraining_validation.get("passed") is False:
            result["pretraining_validation"] = pretraining_validation
            result["pretraining_warnings"] = pretraining_validation.get("failure_reasons", [])

        return result

    if action == "enqueue_train":
        if state["stages"]["reference"]["status"] != "done":
            raise MotionPipelineError("reference stage must be completed before enqueue_train")
        ref_path = _reference_path_in_pipeline(settings, user_id, pid)
        if not ref_path.is_file():
            raise MotionPipelineError("reference_trajectory.json missing in pipeline workspace")
        ref = json.loads(ref_path.read_text(encoding="utf-8"))

        rf = state["stages"]["reference"]
        pretraining = rf.get("pretraining_validation", {})
        if pretraining.get("passed") is False and not force:
            raise MotionPipelineError(
                "Pre-training validation failed. Use force=true to override. "
                f"Issues: {pretraining.get('failure_reasons', [])}"
            )

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
