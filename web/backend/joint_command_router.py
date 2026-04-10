"""
FastAPI router: joint targets (degrees) → radians for DDS / JointController integration.

Merge into the Skill Foundry backend app:

    from joint_command_router import router as joint_command_router
    app.include_router(joint_command_router)

Enable at runtime:

    export G1_JOINT_COMMAND_ENABLED=1

Extend your existing `GET /api/meta` handler to include:

    "joint_command_enabled": <bool from same env>

Wire real hardware / sim by assigning callbacks from your process bootstrap
(after imports that pull in `core_control.joint_controller.JointController`):

    from joint_command_router import set_joint_apply_callbacks

    def apply_rad(map_by_index_str: dict[str, float]) -> None:
        for idx_s, q in map_by_index_str.items():
            jid = int(idx_s)
            ctrl.set_joint(jid, q)
        ctrl.publish()

    def release_all() -> None:
        ctrl.set_all_motors_passive()
        ctrl.publish()

    set_joint_apply_callbacks(apply_rad, release_all)

When callbacks are unset, accepted targets are only stored in memory (useful for tests).
"""

from __future__ import annotations

import math
import os
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["joints"])


def joint_command_enabled() -> bool:
    return os.environ.get("G1_JOINT_COMMAND_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def meta_joint_command_fields() -> dict[str, Any]:
    """Merge into your existing `GET /api/meta` JSON so the web UI enables telemetry joint commands."""
    return {"joint_command_enabled": joint_command_enabled()}


class JointTargetsBody(BaseModel):
    """String keys are joint indices \"0\"…\"28\" (Skill Foundry / Phase 0). Values are degrees."""

    joints_deg: dict[str, float] = Field(default_factory=dict)


_latest_rad: dict[str, float] = {}
_apply_cb: Optional[Callable[[dict[str, float]], None]] = None
_release_cb: Optional[Callable[[], None]] = None


def set_joint_apply_callbacks(
    apply_rad: Optional[Callable[[dict[str, float]], None]],
    release: Optional[Callable[[], None]] = None,
) -> None:
    """Register DDS / lowcmd integration (or None to clear)."""
    global _apply_cb, _release_cb
    _apply_cb = apply_rad
    _release_cb = release


def get_latest_targets_rad() -> dict[str, float]:
    """Last merged targets by index string (radians); empty after release."""
    return dict(_latest_rad)


@router.post("/api/joints/targets")
def post_joint_targets(body: JointTargetsBody) -> dict[str, Any]:
    if not joint_command_enabled():
        raise HTTPException(status_code=404, detail="joint command API disabled")
    delta: dict[str, float] = {}
    for k, deg in body.joints_deg.items():
        try:
            idx = str(int(k))
        except (TypeError, ValueError):
            idx = str(k)
        delta[idx] = math.radians(float(deg))
    _latest_rad.update(delta)
    if _apply_cb is not None:
        try:
            _apply_cb(dict(_latest_rad))
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True, "applied": len(delta)}


@router.post("/api/joints/release")
def post_joint_release() -> dict[str, Any]:
    if not joint_command_enabled():
        raise HTTPException(status_code=404, detail="joint command API disabled")
    _latest_rad.clear()
    if _release_cb is not None:
        try:
            _release_cb()
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True}
