"""FastAPI application: REST + WebSocket contract for G1 Control / Skill Foundry UI."""

from __future__ import annotations

import asyncio
import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import Body, Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from app.config import Settings, get_settings
from app.joint_command import (
    clear_targets as joint_clear_targets,
    meta_joint_command_fields,
    snapshot_targets_rad,
    update_targets_deg,
)
from app.deps import get_user_id
from app.joint_map import GROUPS, JOINT_MAP
from app.platform_db import (
    connect as platform_connect,
    init_schema as platform_init_schema,
    job_get,
    job_list_for_user,
    package_get,
    package_list_visible,
    package_set_published,
)
from app.platform_enqueue import EnqueueError, enqueue_train_job
from app.platform_packaging import run_package_pack
from app.platform_packages import (
    bundle_absolute_path,
    can_download_package,
    register_pack_output,
    register_uploaded_tarball,
)
from app.platform_paths import (
    user_pose_drafts_dir,
    validate_artifact_name,
    validate_pose_draft_name,
)
from app.platform_paths import user_artifacts_dir as platform_user_artifacts_dir
from app.platform_worker import platform_worker_loop
from app.services.discovery import (
    discover_actions,
    discovered_to_json,
    estimate_node_duration_sec,
)
from app.services.motion_validation import run_motion_validation
from app.services.pipeline import (
    run_playback,
    run_preprocess,
    run_train,
    which_skill_foundry,
)
from app.services.dds_joint_bridge import DdsJointBridge, maybe_start_dds_joint_bridge
from app.services.motion_pipeline import (
    MotionPipelineError,
    get_motion_pipeline_state,
    run_motion_pipeline_action,
)
from app.services.retargeting import parse_landmarks_payload, run_retargeting
from app.services.telemetry import mock_telemetry_stream
from app.services.validation import validate_payload
from app.services.cortex_api import router as cortex_router
from app.services.video_ingest import (
    VideoIngestError,
    get_video_metadata,
    ingest_youtube_video,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    p = s.platform_sqlite_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = platform_connect(p)
    try:
        platform_init_schema(conn)
    finally:
        conn.close()

    dds_bridge: DdsJointBridge | None = maybe_start_dds_joint_bridge(s)

    stop = asyncio.Event()
    worker_task: asyncio.Task[None] | None = None
    if s.platform_worker_enabled:
        worker_task = asyncio.create_task(platform_worker_loop(s, stop))

    yield

    stop.set()
    if worker_task is not None:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    if dds_bridge is not None:
        dds_bridge.stop()


app = FastAPI(
    title="G1 Control Web API",
    description="Backend for Skill Foundry authoring UI: validation, discovery, CLI pipeline, telemetry WebSocket.",
    version="0.1.0",
    lifespan=lifespan,
)

_cors_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cortex_router)


class ValidateRequest(BaseModel):
    kind: Literal[
        "keyframes",
        "motion",
        "scenario",
        "reference_trajectory",
        "demonstration_dataset",
    ]
    payload: dict[str, Any]


class PreprocessRequest(BaseModel):
    keyframes: dict[str, Any]
    frequency_hz: float | None = Field(default=None, description="Default 50 Hz")
    validate_motion: bool = Field(
        default=True,
        description="After success, run motion validation on reference_trajectory (kinematics, optional RNEA, MuJoCo)",
    )
    mjcf_path: str | None = Field(
        default=None,
        description="Override MJCF for collision check; default from server G1_MJCF_PATH / unitree_mujoco scene",
    )


class ValidateMotionRequest(BaseModel):
    reference_trajectory: dict[str, Any]
    mjcf_path: str | None = Field(
        default=None,
        description="MJCF for self-collision; default from server settings",
    )


class RetargetRequest(BaseModel):
    landmarks: list[Any] = Field(description="[33,3] for single frame or [N,33,3] for sequence")
    source_skeleton: str = "mediapipe_pose_33"
    target_robot: str = "unitree_g1_29dof"
    clip_to_limits: bool = True

    @model_validator(mode="after")
    def _validate_landmarks_shape(self) -> RetargetRequest:
        parse_landmarks_payload(self.landmarks)
        return self


class RetargetResponse(BaseModel):
    joint_order: list[str]
    joint_angles_rad: list[float] | list[list[float]]
    source_skeleton: str
    target_robot: str
    mapping_version: str
    frame_count: int
    dropped_frames: int
    warnings: list[str]
    timing_ms: float


class PlaybackRequest(BaseModel):
    reference_trajectory: dict[str, Any] | None = None
    reference_path: str | None = None
    mjcf_path: str | None = None
    mode: Literal["dynamic", "kinematic"] = "dynamic"
    dt: float = 0.005
    kp: float = 150.0
    kd: float = 5.0
    seed: int = 0
    max_steps: int | None = None
    write_demonstration_json: bool = False


class TrainRequest(BaseModel):
    config: dict[str, Any] | None = None
    config_path: str | None = None
    reference_path: str
    demonstration_path: str | None = None
    mode: Literal["smoke", "train", "amp"] = "smoke"
    eval_only: bool = False
    checkpoint_path: str | None = Field(
        default=None,
        description="Local policy .zip for AMP eval-only (requires eval_only and mode amp).",
    )


class CreateTrainJobRequest(BaseModel):
    """Async training job (Phase 5): isolated workspace under platform data dir.

    ``config`` is optional: omitted or empty becomes ``{}``. The server merges
    ``output_dir`` into the written ``train_config.json`` before ``skill-foundry-train``.
    """

    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Train CLI JSON config; server adds output_dir in the job workspace.",
    )
    mode: Literal["smoke", "train", "amp"] = "smoke"
    reference_trajectory: dict[str, Any] | None = None
    reference_artifact: str | None = None
    demonstration_dataset: dict[str, Any] | None = None
    demonstration_artifact: str | None = None
    eval_only: bool = False
    checkpoint_artifact: str | None = Field(
        default=None,
        description="User artifact filename (under /api/platform/artifacts) for AMP eval-only.",
    )
    motion_export: dict[str, Any] | None = Field(
        default=None,
        description="Optional motion manifest hints (retarget version, etc.) stored in workspace.",
    )

    @model_validator(mode="after")
    def _validate_sources(self) -> CreateTrainJobRequest:
        has_ref_obj = self.reference_trajectory is not None
        has_ref_art = self.reference_artifact is not None
        if has_ref_obj == has_ref_art:
            raise ValueError("Provide exactly one of reference_trajectory or reference_artifact")
        if self.demonstration_dataset is not None and self.demonstration_artifact:
            raise ValueError("Provide at most one of demonstration_dataset or demonstration_artifact")
        if self.eval_only:
            if self.mode != "amp":
                raise ValueError("eval_only requires mode amp")
            if not self.checkpoint_artifact:
                raise ValueError("eval_only requires checkpoint_artifact")
        elif self.checkpoint_artifact:
            raise ValueError("checkpoint_artifact is only valid when eval_only is true")
        return self


class PackagePatchBody(BaseModel):
    published: bool


class MotionPipelineRunRequest(BaseModel):
    """Phase 6 orchestration: idempotent stages keyed by ``pipeline_id``."""

    pipeline_id: str
    action: Literal[
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
    force: bool = False
    capture_artifact: str | None = None
    landmarks_artifact: str | None = None
    bvh_artifact: str | None = None
    reference_artifact: str | None = None
    frequency_hz: float = Field(default=50.0, gt=0)
    train_config: dict[str, Any] = Field(default_factory=dict)
    train_mode: Literal["smoke", "train", "amp"] = "amp"
    demonstration_dataset: dict[str, Any] | None = None
    demonstration_artifact: str | None = None
    eval_only: bool = False
    checkpoint_artifact: str | None = None
    motion_export: dict[str, Any] | None = None
    source_skeleton: str = "mediapipe_pose_33"
    target_robot: str = "unitree_g1_29dof"
    clip_to_limits: bool = True
    preprocess_filter: Literal["savgol", "kalman", "both"] = "both"
    preprocess_window_length: int = Field(default=7, ge=3)
    preprocess_polyorder: int = Field(default=2, ge=0)
    preprocess_confidence_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    preprocess_process_noise: float = Field(default=0.01, gt=0.0)
    preprocess_measurement_noise: float = Field(default=0.1, gt=0.0)


class JointTargetsBody(BaseModel):
    """Motor indices \"0\"…\"28\" (degrees), same as Skill Foundry Phase 0."""

    joints_deg: dict[str, float] = Field(default_factory=dict)


class ScenarioNode(BaseModel):
    subdir: str
    action_name: str
    speed: float = 0.5
    repeat: int = 1
    keyframe_count: int | None = None


class ScenarioEstimateRequest(BaseModel):
    nodes: list[ScenarioNode]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    s = get_settings()
    out: dict[str, Any] = {
        "repo_root": str(s.repo_root.resolve()),
        "sdk_python_root": str(s.resolved_sdk_root()),
        "skill_foundry_python_root": str(s.resolved_skill_foundry_root()),
        "mjcf_default": str(s.resolved_mjcf()) if s.resolved_mjcf() else None,
        "telemetry_mode": "dds" if s.use_dds_telemetry else "mock",
        "platform_worker_enabled": bool(s.platform_worker_enabled),
        "job_timeout_sec": float(s.job_timeout_sec),
        "retargeting_enabled": True,
        "retargeting_source_skeleton": "mediapipe_pose_33",
        "retargeting_target_robot": "unitree_g1_29dof",
        "motion_pipeline_enabled": True,
        "motion_publish_max_mse": s.motion_publish_max_mse,
    }
    out.update(meta_joint_command_fields(bool(s.joint_command_enabled)))
    out["dds_joint_bridge"] = bool(s.dds_joint_bridge)
    out["dds_joint_publish_hz"] = float(s.dds_joint_publish_hz)
    return out


@app.post("/api/joints/targets")
def post_joint_targets(body: JointTargetsBody) -> dict[str, Any]:
    s = get_settings()
    if not s.joint_command_enabled:
        raise HTTPException(status_code=404, detail="joint command API disabled")
    n = update_targets_deg(body.joints_deg)
    return {"ok": True, "applied": n}


@app.post("/api/joints/release")
def post_joint_release() -> dict[str, Any]:
    s = get_settings()
    if not s.joint_command_enabled:
        raise HTTPException(status_code=404, detail="joint command API disabled")
    joint_clear_targets()
    return {"ok": True}


@app.get("/api/joints")
def joints() -> dict[str, Any]:
    return {
        "joint_map": {str(k): v for k, v in JOINT_MAP.items()},
        "groups": [{"name": n, "indices": idx} for n, idx in GROUPS],
    }


@app.get("/api/pipeline/detect-cli")
def detect_cli() -> dict[str, Any]:
    return {"commands": which_skill_foundry()}


@app.post("/api/validate")
def validate(req: ValidateRequest) -> dict[str, Any]:
    s = get_settings()
    return validate_payload(
        req.kind,
        req.payload,
        s.resolved_sdk_root(),
        s.resolved_skill_foundry_root(),
    )


@app.get("/api/mid-level/actions")
def mid_level_actions() -> dict[str, Any]:
    s = get_settings()
    actions = discover_actions(s.resolved_skill_foundry_root())
    return {"actions": discovered_to_json(actions)}


@app.post("/api/scenario/estimate")
def scenario_estimate(req: ScenarioEstimateRequest) -> dict[str, Any]:
    s = get_settings()
    discovered = discover_actions(s.resolved_skill_foundry_root())
    actions = {f"{a.subdir}/{a.action_name}": a.keyframe_count for a in discovered}
    nodes: list[dict[str, Any]] = []
    total = 0.0
    for n in req.nodes:
        kc = n.keyframe_count
        if kc is None:
            kc = actions.get(f"{n.subdir}/{n.action_name}", 1)
        dur = estimate_node_duration_sec(kc, n.speed, n.repeat)
        total += dur
        nodes.append(
            {
                "subdir": n.subdir,
                "action_name": n.action_name,
                "speed": n.speed,
                "repeat": n.repeat,
                "keyframe_count": kc,
                "estimated_seconds": dur,
            }
        )
    return {"nodes": nodes, "total_estimated_seconds": total}


@app.post("/api/pipeline/preprocess")
async def pipeline_preprocess(req: PreprocessRequest) -> dict[str, Any]:
    s = get_settings()
    mjcf: str | None = None
    if req.mjcf_path:
        p = Path(req.mjcf_path)
        if p.is_file():
            mjcf = str(p.resolve())
    else:
        m = s.resolved_mjcf()
        mjcf = str(m) if m is not None else None
    return await run_preprocess(
        s.resolved_sdk_root(),
        s.resolved_skill_foundry_root(),
        req.keyframes,
        req.frequency_hz,
        validate_motion=req.validate_motion,
        mjcf_path=mjcf,
    )


@app.post("/api/pipeline/validate-motion")
def pipeline_validate_motion(req: ValidateMotionRequest) -> dict[str, Any]:
    """Validate a ReferenceTrajectory v1 (offline checks before playback)."""
    s = get_settings()
    mjcf: str | None = None
    if req.mjcf_path:
        p = Path(req.mjcf_path)
        if p.is_file():
            mjcf = str(p.resolve())
    else:
        m = s.resolved_mjcf()
        mjcf = str(m) if m is not None else None
    report = run_motion_validation(
        s.resolved_sdk_root(),
        s.resolved_skill_foundry_root(),
        req.reference_trajectory,
        mjcf,
        validate_motion=True,
    )
    if report is None:
        return {"ok": False, "issues": [], "notes": ["motion validation skipped"]}
    return report


@app.post("/api/pipeline/motion/run")
async def motion_pipeline_run(
    req: MotionPipelineRunRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    s = get_settings()
    try:
        return await run_motion_pipeline_action(
            s,
            user_id,
            pipeline_id=req.pipeline_id,
            action=req.action,
            capture_artifact=req.capture_artifact,
            landmarks_artifact=req.landmarks_artifact,
            bvh_artifact=req.bvh_artifact,
            reference_artifact=req.reference_artifact,
            frequency_hz=req.frequency_hz,
            force=req.force,
            train_config=req.train_config,
            train_mode=req.train_mode,
            demonstration_dataset=req.demonstration_dataset,
            demonstration_artifact=req.demonstration_artifact,
            eval_only=req.eval_only,
            checkpoint_artifact=req.checkpoint_artifact,
            motion_export=req.motion_export,
            source_skeleton=req.source_skeleton,
            target_robot=req.target_robot,
            clip_to_limits=req.clip_to_limits,
            preprocess_filter=req.preprocess_filter,
            preprocess_window_length=req.preprocess_window_length,
            preprocess_polyorder=req.preprocess_polyorder,
            preprocess_confidence_threshold=req.preprocess_confidence_threshold,
            preprocess_process_noise=req.preprocess_process_noise,
            preprocess_measurement_noise=req.preprocess_measurement_noise,
        )
    except MotionPipelineError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/pipeline/motion/{pipeline_id}")
def motion_pipeline_status(
    pipeline_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    try:
        return get_motion_pipeline_state(get_settings(), user_id, pipeline_id)
    except MotionPipelineError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.post("/api/pipeline/retarget")
def pipeline_retarget(req: RetargetRequest) -> RetargetResponse:
    s = get_settings()
    frames, is_sequence = parse_landmarks_payload(req.landmarks)
    try:
        result = run_retargeting(
            sdk_root=s.resolved_sdk_root(),
            skill_foundry_root=s.resolved_skill_foundry_root(),
            frames=frames,
            source_skeleton=req.source_skeleton,
            target_robot=req.target_robot,
            clip_to_limits=req.clip_to_limits,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"retarget failure: {e}") from e

    joint_angles_payload: list[float] | list[list[float]]
    if is_sequence:
        joint_angles_payload = result.joint_angles_rad.tolist()
    else:
        joint_angles_payload = result.joint_angles_rad[0].tolist()

    return RetargetResponse(
        joint_order=result.joint_order,
        joint_angles_rad=joint_angles_payload,
        source_skeleton=result.source_skeleton,
        target_robot=result.target_robot,
        mapping_version=result.mapping_version,
        frame_count=int(result.joint_angles_rad.shape[0]),
        dropped_frames=0,
        warnings=result.warnings,
        timing_ms=result.elapsed_ms,
    )


@app.post("/api/pipeline/playback")
async def pipeline_playback(req: PlaybackRequest) -> dict[str, Any]:
    s = get_settings()
    sdk = s.resolved_sdk_root()
    sf = s.resolved_skill_foundry_root()
    mjcf = None
    if req.mjcf_path:
        mjcf = Path(req.mjcf_path)
    else:
        mjcf = s.resolved_mjcf()
    if mjcf is None or not mjcf.is_file():
        return {
            "exit_code": 2,
            "stdout": "",
            "stderr": "MJCF not found. Set G1_MJCF_PATH or place unitree_mujoco scene at default path.",
            "output_npz": None,
            "demonstration_dataset_json": None,
        }

    ref_path: Path
    td_ctx = None
    if req.reference_path:
        ref_path = Path(req.reference_path).resolve()
        if not ref_path.is_file():
            return {
                "exit_code": 2,
                "stdout": "",
                "stderr": f"reference file not found: {ref_path}",
                "output_npz": None,
                "demonstration_dataset_json": None,
            }
    elif req.reference_trajectory:
        td = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(req.reference_trajectory, td, indent=2)
        td.close()
        ref_path = Path(td.name)
    else:
        return {
            "exit_code": 2,
            "stdout": "",
            "stderr": "Provide reference_trajectory JSON body or reference_path",
            "output_npz": None,
            "demonstration_dataset_json": None,
        }

    try:
        result = await run_playback(
            sdk,
            sf,
            ref_path,
            mjcf,
            mode=req.mode,
            dt=req.dt,
            kp=req.kp,
            kd=req.kd,
            seed=req.seed,
            max_steps=req.max_steps,
            demonstration_json=req.write_demonstration_json,
        )
    finally:
        if req.reference_trajectory and ref_path.is_file() and str(ref_path).startswith(tempfile.gettempdir()):
            try:
                ref_path.unlink(missing_ok=True)
            except OSError:
                pass

    return result


@app.post("/api/pipeline/train")
async def pipeline_train(req: TrainRequest) -> dict[str, Any]:
    s = get_settings()
    sdk = s.resolved_sdk_root()
    sf = s.resolved_skill_foundry_root()
    ref = Path(req.reference_path).resolve()
    if not ref.is_file():
        return {"exit_code": 2, "stdout": "", "stderr": f"reference not found: {ref}"}

    cfg_path: Path
    if req.config_path:
        cfg_path = Path(req.config_path).resolve()
    elif req.config is not None:
        td = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(req.config, td, indent=2)
        td.close()
        cfg_path = Path(td.name)
    else:
        return {"exit_code": 2, "stdout": "", "stderr": "Provide config or config_path"}

    demo: Path | None = None
    if req.demonstration_path:
        demo = Path(req.demonstration_path).resolve()
        if not demo.is_file():
            return {"exit_code": 2, "stdout": "", "stderr": f"demonstration not found: {demo}"}

    eval_kw: dict[str, Any] = {}
    if req.eval_only:
        if req.mode != "amp":
            return {
                "exit_code": 2,
                "stdout": "",
                "stderr": "eval_only requires mode amp",
            }
        if not req.checkpoint_path:
            return {
                "exit_code": 2,
                "stdout": "",
                "stderr": "eval_only requires checkpoint_path",
            }
        ck = Path(req.checkpoint_path).expanduser().resolve()
        if not ck.is_file():
            return {
                "exit_code": 2,
                "stdout": "",
                "stderr": f"checkpoint not found: {ck}",
            }
        eval_out = ck.parent / "eval_motion.json"
        eval_kw = {
            "eval_only": True,
            "eval_checkpoint": ck,
            "eval_output": eval_out,
        }

    try:
        return await run_train(
            sdk, sf, cfg_path, ref, demo, mode=req.mode, **eval_kw
        )
    finally:
        if req.config is not None and cfg_path.is_file() and str(cfg_path).startswith(tempfile.gettempdir()):
            try:
                cfg_path.unlink(missing_ok=True)
            except OSError:
                pass


def _job_row_public(
    settings: Settings, row: dict[str, Any]
) -> dict[str, Any]:
    root = settings.resolved_platform_data_dir()
    ws = root / row["workspace_relpath"]
    out: dict[str, Any] = {
        "job_id": row["id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "mode": row["mode"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "exit_code": row["exit_code"],
        "error_message": row["error_message"],
        "workspace_relpath": row["workspace_relpath"],
    }
    log_out = ws / "train_stdout.log"
    log_err = ws / "train_stderr.log"
    if log_out.is_file():
        t = log_out.read_text(encoding="utf-8", errors="replace")
        out["stdout_tail"] = t[-8000:]
    if log_err.is_file():
        t = log_err.read_text(encoding="utf-8", errors="replace")
        out["stderr_tail"] = t[-8000:]
    return out


@app.post("/api/platform/artifacts/{name}")
async def platform_put_artifact(
    name: str,
    user_id: str = Depends(get_user_id),
    body: dict[str, Any] = Body(...),
) -> dict[str, str]:
    try:
        validate_artifact_name(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    s = get_settings()
    root = s.resolved_platform_data_dir()
    d = platform_user_artifacts_dir(root, user_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return {"artifact": name, "path": str(path.resolve())}


@app.post("/api/jobs/train")
async def jobs_train_enqueue(
    req: CreateTrainJobRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    s = get_settings()
    try:
        jid = enqueue_train_job(
            s,
            user_id,
            config=req.config,
            mode=req.mode,
            reference_trajectory=req.reference_trajectory,
            reference_artifact=req.reference_artifact,
            demonstration_dataset=req.demonstration_dataset,
            demonstration_artifact=req.demonstration_artifact,
            eval_only=req.eval_only,
            checkpoint_artifact=req.checkpoint_artifact,
            motion_export=req.motion_export,
        )
    except EnqueueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"job_id": jid, "status": "queued"}


@app.get("/api/jobs")
def jobs_list(
    user_id: str = Depends(get_user_id),
    limit: int = 50,
) -> dict[str, Any]:
    s = get_settings()
    rows = job_list_for_user(s.platform_sqlite_path(), user_id, limit=max(1, min(limit, 200)))
    return {"jobs": [_job_row_public(s, r) for r in rows]}


@app.get("/api/jobs/{job_id}")
def jobs_get(
    job_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    s = get_settings()
    row = job_get(s.platform_sqlite_path(), job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    if row["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="not allowed")
    return _job_row_public(s, row)


@app.post("/api/packages/from-job/{job_id}")
async def packages_from_job(
    job_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    s = get_settings()
    db_path = s.platform_sqlite_path()
    row = job_get(db_path, job_id)
    if not row or row["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    if row["status"] != "succeeded":
        raise HTTPException(status_code=409, detail="job must be succeeded")
    root = s.resolved_platform_data_dir()
    workspace = root / row["workspace_relpath"]
    train_out = workspace / "train_out"
    cfg = workspace / "train_config.json"
    ref = workspace / "reference_trajectory.json"
    if not train_out.is_dir() or not cfg.is_file() or not ref.is_file():
        raise HTTPException(status_code=409, detail="missing train_out or config/reference in workspace")
    tmp_out = workspace / f"pack_{job_id}.tar.gz"
    sdk = s.resolved_sdk_root()
    sf = s.resolved_skill_foundry_root()
    result = await run_package_pack(
        sdk,
        sf,
        train_config=cfg,
        reference_trajectory=ref,
        run_dir=train_out,
        output_archive=tmp_out,
    )
    if int(result.get("exit_code") or 1) != 0:
        raise HTTPException(
            status_code=500,
            detail={"message": "skill-foundry-package failed", "stderr": result.get("stderr")},
        )
    pid = register_pack_output(
        s,
        user_id,
        archive_path=tmp_out,
        label=None,
        train_output_dir=train_out,
    )
    return {"package_id": pid}


@app.post("/api/packages/upload")
async def packages_upload(
    user_id: str = Depends(get_user_id),
    file: UploadFile = File(...),
    label: str | None = None,
) -> dict[str, str]:
    if not file.filename or not file.filename.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="expected .tar.gz skill bundle")
    s = get_settings()
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf:
        tmp = Path(tf.name)
    try:
        content = await file.read()
        tmp.write_bytes(content)
        pid = register_uploaded_tarball(s, user_id, src_path=tmp, label=label)
    finally:
        tmp.unlink(missing_ok=True)
    return {"package_id": pid}


@app.get("/api/packages")
def packages_list(
    user_id: str = Depends(get_user_id),
    limit: int = 100,
) -> dict[str, Any]:
    s = get_settings()
    rows = package_list_visible(s.platform_sqlite_path(), user_id, limit=max(1, min(limit, 500)))
    out = []
    for r in rows:
        rd = dict(r)
        out.append(
            {
                "package_id": rd["id"],
                "owner_user_id": rd["user_id"],
                "label": rd["label"],
                "published": bool(rd["published"]),
                "created_at": rd["created_at"],
                "manifest_summary": rd["manifest_summary"],
                "validation_passed": rd.get("validation_passed"),
                "validation_summary": rd.get("validation_summary"),
            }
        )
    return {"packages": out}


class PoseDraftRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    document: dict[str, Any]


@app.post("/api/platform/pose-drafts")
def save_pose_draft(
    req: PoseDraftRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    """Persist a keyframes JSON (or similar) from client-side MuJoCo pose authoring."""
    s = get_settings()
    try:
        safe_name = validate_pose_draft_name(req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    root = s.resolved_platform_data_dir()
    out_dir = user_pose_drafts_dir(root, user_id)
    path = (out_dir / f"{safe_name}.json").resolve()
    if not str(path).startswith(str(out_dir.resolve())):
        raise HTTPException(status_code=400, detail="invalid path")
    path.write_text(json.dumps(req.document, indent=2), encoding="utf-8")
    rel = path.relative_to(root)
    return {"path": str(rel).replace("\\", "/")}


@app.get("/api/packages/{package_id}/download")
def packages_download(
    package_id: str,
    user_id: str = Depends(get_user_id),
) -> FileResponse:
    s = get_settings()
    row = package_get(s.platform_sqlite_path(), package_id)
    if not row:
        raise HTTPException(status_code=404, detail="package not found")
    if not can_download_package(s, row, user_id):
        raise HTTPException(status_code=403, detail="not allowed")
    path = bundle_absolute_path(s, row["bundle_relpath"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="bundle file missing")
    return FileResponse(
        path,
        filename="skill_bundle.tar.gz",
        media_type="application/gzip",
    )


@app.patch("/api/packages/{package_id}")
def packages_patch(
    package_id: str,
    body: PackagePatchBody,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    s = get_settings()
    db_path = s.platform_sqlite_path()
    row = package_get(db_path, package_id)
    if not row or row["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="package not found or not owner")

    if body.published and not s.skip_validation_gate:
        vp = row.get("validation_passed")
        if vp != 1:
            vsum_raw = row.get("validation_summary")
            extra: dict[str, Any] = {}
            if isinstance(vsum_raw, str) and vsum_raw.strip():
                try:
                    extra = json.loads(vsum_raw)
                except json.JSONDecodeError:
                    extra = {}
            reasons = extra.get("failure_reasons")
            if not reasons and extra.get("error"):
                reasons = [{"code": "validation_error", "message": str(extra["error"])}]
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Publishing requires a successful product validation report "
                        "(validation_passed). Re-train with product validation enabled, "
                        "or use G1_SKIP_VALIDATION_GATE=1 in development only."
                    ),
                    "validation_passed": vp,
                    "failure_reasons": reasons,
                    "metrics": extra.get("metrics"),
                },
            )

        from app.services.sdk_path import ensure_sdk_on_path

        ensure_sdk_on_path(s.resolved_sdk_root(), s.resolved_skill_foundry_root())
        from skill_foundry_export.motion_bundle_validate import (
            read_manifest_from_tarball,
            validate_motion_skill_bundle,
        )

        bpath = bundle_absolute_path(s, row["bundle_relpath"])
        man = read_manifest_from_tarball(bpath)
        if isinstance(man, dict) and isinstance(man.get("motion"), dict):
            mv = validate_motion_skill_bundle(
                bpath,
                require_motion_section=True,
                max_tracking_mse=s.motion_publish_max_mse,
            )
            if not mv.passed:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": (
                            "Publishing this motion skill bundle failed validation "
                            "(manifest.motion requires eval_motion.json and optional MSE cap)."
                        ),
                        "motion_validation_passed": False,
                        "failure_reasons": mv.reasons,
                        "metrics": mv.metrics,
                    },
                )

    ok = package_set_published(db_path, package_id, user_id, body.published)
    if not ok:
        raise HTTPException(status_code=404, detail="package not found or not owner")
    row = package_get(db_path, package_id)
    assert row is not None
    return {
        "package_id": row["id"],
        "published": bool(row["published"]),
    }


class VideoIngestRequest(BaseModel):
    """Request to ingest a YouTube video for motion extraction."""

    youtube_url: str = Field(..., description="YouTube video URL")
    start_sec: float | None = Field(default=None, description="Start time for trimming")
    end_sec: float | None = Field(default=None, description="End time for trimming")
    max_duration_sec: float = Field(default=120.0, description="Maximum allowed duration")


class VideoProcessRequest(BaseModel):
    """Request to process video for pose extraction."""

    video_id: str = Field(..., description="Video ID from ingestion")
    target_fps: float = Field(default=30.0, description="Target FPS for extraction")
    start_sec: float | None = Field(default=None, description="Start time")
    end_sec: float | None = Field(default=None, description="End time")


@app.post("/api/video/ingest")
async def video_ingest(
    req: VideoIngestRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Ingest a YouTube video for motion extraction.

    Downloads the video and stores it in the user's workspace.
    """
    s = get_settings()
    try:
        result = ingest_youtube_video(
            s,
            user_id,
            req.youtube_url,
            start_sec=req.start_sec,
            end_sec=req.end_sec,
            max_duration_sec=req.max_duration_sec,
        )
        return {
            "video_id": result.video_id,
            "duration_sec": result.duration_sec,
            "fps": result.fps,
            "width": result.width,
            "height": result.height,
            "title": result.title,
            "artifact_path": result.artifact_path,
        }
    except VideoIngestError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/video/{video_id}")
def video_get(
    video_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Get metadata for a previously ingested video."""
    s = get_settings()
    metadata = get_video_metadata(s, user_id, video_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return metadata


@app.post("/api/video/process")
async def video_process_enqueue(
    req: VideoProcessRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    """Enqueue video processing job for pose extraction.

    Returns a job_id that can be used to check status.
    """
    from app.platform_enqueue import enqueue_video_process_job

    s = get_settings()

    metadata = get_video_metadata(s, user_id, req.video_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Video not found")

    try:
        job_id = enqueue_video_process_job(
            s,
            user_id,
            video_id=req.video_id,
            video_artifact=metadata["file_path"],
            target_fps=req.target_fps,
            start_sec=req.start_sec,
            end_sec=req.end_sec,
        )
        return {"job_id": job_id, "status": "queued"}
    except EnqueueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
    await ws.accept()
    s = get_settings()
    if s.use_dds_telemetry:
        await ws.send_json(
            {
                "type": "error",
                "message": "DDS telemetry bridge not implemented in this build; use mock (G1_USE_DDS_TELEMETRY=0).",
            }
        )
        await ws.close()
        return

    try:
        getter = snapshot_targets_rad if s.joint_command_enabled else None
        async for line in mock_telemetry_stream(
            s.telemetry_mock_hz,
            command_rad_getter=getter,
        ):
            await ws.send_text(line.strip())
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise


def create_app() -> FastAPI:
    return app
