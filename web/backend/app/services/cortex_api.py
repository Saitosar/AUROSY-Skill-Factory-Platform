"""Cortex Pipeline API — NMR correction and RL training endpoints.

Provides REST endpoints for the "Cortex" (brain cortex) layer:
- Trajectory correction (IK + collision fixing)
- Training job submission
- Result retrieval
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.deps import get_user_id


router = APIRouter(prefix="/api/cortex", tags=["cortex"])


class CortexCorrectRequest(BaseModel):
    """Request to correct a trajectory using NMR pipeline."""

    animation_json: dict[str, Any] = Field(
        ...,
        description="ReferenceTrajectory JSON from UI editor",
    )
    options: dict[str, Any] = Field(
        default_factory=lambda: {
            "fix_collisions": True,
            "fix_joint_limits": True,
        },
        description="Correction options",
    )


class CortexCorrectResponse(BaseModel):
    """Response with corrected trajectory."""

    corrected_json: dict[str, Any]
    issues_fixed: list[dict[str, Any]]
    metadata: dict[str, Any]


class CortexTrainRequest(BaseModel):
    """Request to start RL training job."""

    reference_json: dict[str, Any] = Field(
        ...,
        description="Corrected ReferenceTrajectory for training",
    )
    config: dict[str, Any] = Field(
        default_factory=lambda: {
            "total_timesteps": 100_000,
            "reward_weights": {
                "w_track": 1.0,
                "w_collision": 10.0,
            },
        },
        description="Training configuration",
    )
    name: str = Field(
        default="cortex_training",
        description="Job name for identification",
    )


class CortexTrainResponse(BaseModel):
    """Response with training job info."""

    job_id: str
    status: str
    message: str


class CortexResultResponse(BaseModel):
    """Response with training result."""

    job_id: str
    status: str
    result_json: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    error: str | None = None


@router.post("/correct", response_model=CortexCorrectResponse)
def cortex_correct(
    req: CortexCorrectRequest,
    settings: Settings = Depends(get_settings),
    user_id: str = Depends(get_user_id),
) -> CortexCorrectResponse:
    """Correct trajectory using NMR pipeline (IK + collision fixing).
    
    Takes user-generated animation JSON and returns physics-corrected version.
    """
    try:
        from skill_foundry_nmr import (
            correct_reference_trajectory,
            fix_reference_trajectory,
        )
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"NMR module not available: {e}",
        ) from e
    
    reference = req.animation_json
    options = req.options
    issues_fixed: list[dict[str, Any]] = []
    
    if not reference.get("joint_positions") or not reference.get("joint_order"):
        raise HTTPException(
            status_code=400,
            detail="Invalid reference: missing joint_positions or joint_order",
        )
    
    corrected = reference.copy()
    
    if options.get("fix_joint_limits", True):
        try:
            corrected = correct_reference_trajectory(corrected)
            ik_meta = corrected.get("_ik_metadata", {})
            if ik_meta.get("joint_limit_violations", 0) > 0:
                issues_fixed.append({
                    "type": "joint_limits",
                    "count": ik_meta.get("joint_limit_violations"),
                    "frames_affected": ik_meta.get("frames_corrected"),
                })
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"IK correction failed: {e}",
            ) from e
    
    if options.get("fix_collisions", True):
        mjcf_path = settings.default_mjcf_path
        if not mjcf_path or not Path(mjcf_path).exists():
            raise HTTPException(
                status_code=503,
                detail="MJCF path not configured for collision detection",
            )
        
        try:
            corrected = fix_reference_trajectory(corrected, mjcf_path)
            nmr_meta = corrected.get("_nmr_metadata", {})
            if nmr_meta.get("frames_fixed", 0) > 0:
                issues_fixed.append({
                    "type": "self_collision",
                    "count": nmr_meta.get("total_corrections"),
                    "frames_affected": nmr_meta.get("frames_fixed"),
                })
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Collision fixing failed: {e}",
            ) from e
    
    for key in list(corrected.keys()):
        if key.startswith("_"):
            del corrected[key]
    
    return CortexCorrectResponse(
        corrected_json=corrected,
        issues_fixed=issues_fixed,
        metadata={
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "options_applied": options,
        },
    )


@router.post("/train", response_model=CortexTrainResponse)
def cortex_train(
    req: CortexTrainRequest,
    settings: Settings = Depends(get_settings),
    user_id: str = Depends(get_user_id),
) -> CortexTrainResponse:
    """Submit RL training job for trajectory.
    
    Training runs asynchronously. Use GET /api/cortex/result/{job_id} to check status.
    """
    job_id = f"cortex_{uuid.uuid4().hex[:12]}"
    
    jobs_dir = Path(settings.resolved_platform_data_dir()) / "cortex_jobs" / user_id
    jobs_dir.mkdir(parents=True, exist_ok=True)
    
    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "name": req.name,
        "config": req.config,
        "reference_json": req.reference_json,
    }
    
    job_path = jobs_dir / f"{job_id}.json"
    job_path.write_text(json.dumps(job_data, indent=2), encoding="utf-8")
    
    return CortexTrainResponse(
        job_id=job_id,
        status="queued",
        message=f"Training job {job_id} queued. Use Vast.ai for GPU training.",
    )


@router.get("/result/{job_id}", response_model=CortexResultResponse)
def cortex_result(
    job_id: str,
    settings: Settings = Depends(get_settings),
    user_id: str = Depends(get_user_id),
) -> CortexResultResponse:
    """Get training job result.
    
    Returns current status and result JSON if training is complete.
    """
    jobs_dir = Path(settings.resolved_platform_data_dir()) / "cortex_jobs" / user_id
    job_path = jobs_dir / f"{job_id}.json"
    
    if not job_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_data = json.loads(job_path.read_text())
    
    result_path = jobs_dir / f"{job_id}_result.json"
    result_json = None
    metrics = None
    
    if result_path.exists():
        result_data = json.loads(result_path.read_text())
        result_json = result_data.get("result_json")
        metrics = result_data.get("metrics")
        job_data["status"] = "completed"
    
    return CortexResultResponse(
        job_id=job_id,
        status=job_data.get("status", "unknown"),
        result_json=result_json,
        metrics=metrics,
        error=job_data.get("error"),
    )


@router.get("/jobs")
def cortex_jobs(
    settings: Settings = Depends(get_settings),
    user_id: str = Depends(get_user_id),
) -> list[dict[str, Any]]:
    """List all Cortex training jobs for current user."""
    jobs_dir = Path(settings.resolved_platform_data_dir()) / "cortex_jobs" / user_id
    
    if not jobs_dir.exists():
        return []
    
    jobs = []
    for job_path in jobs_dir.glob("cortex_*.json"):
        if "_result" in job_path.name:
            continue
        try:
            job_data = json.loads(job_path.read_text())
            jobs.append({
                "job_id": job_data.get("job_id"),
                "name": job_data.get("name"),
                "status": job_data.get("status"),
                "created_at": job_data.get("created_at"),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    
    jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return jobs


@router.delete("/jobs/{job_id}")
def cortex_delete_job(
    job_id: str,
    settings: Settings = Depends(get_settings),
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    """Delete a Cortex training job."""
    jobs_dir = Path(settings.resolved_platform_data_dir()) / "cortex_jobs" / user_id
    job_path = jobs_dir / f"{job_id}.json"
    result_path = jobs_dir / f"{job_id}_result.json"
    
    if not job_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_path.unlink()
    if result_path.exists():
        result_path.unlink()
    
    return {"status": "deleted", "job_id": job_id}
