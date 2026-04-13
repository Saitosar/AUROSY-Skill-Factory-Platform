"""Create isolated job workspaces and enqueue training jobs."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal

from app.config import Settings
from app.platform_db import job_insert
from app.platform_paths import (
    job_workspace,
    user_artifacts_dir,
    validate_artifact_name,
    workspace_relpath,
)


class EnqueueError(ValueError):
    pass


POLICY_CHECKPOINT_WS_NAME = "policy_checkpoint.zip"
PLATFORM_MOTION_META_NAME = "platform_motion.json"


def enqueue_train_job(
    settings: Settings,
    user_id: str,
    *,
    config: dict[str, Any],
    mode: Literal["smoke", "train", "amp"],
    reference_trajectory: dict[str, Any] | None,
    reference_artifact: str | None,
    demonstration_dataset: dict[str, Any] | None,
    demonstration_artifact: str | None,
    eval_only: bool = False,
    checkpoint_artifact: str | None = None,
    motion_export: dict[str, Any] | None = None,
) -> str:
    if reference_trajectory is None and not reference_artifact:
        raise EnqueueError("provide reference_trajectory or reference_artifact")
    if reference_trajectory is not None and reference_artifact is not None:
        raise EnqueueError("use only one of reference_trajectory or reference_artifact")

    if demonstration_dataset is not None and demonstration_artifact:
        raise EnqueueError("use only one of demonstration_dataset or demonstration_artifact")

    if eval_only:
        if mode != "amp":
            raise EnqueueError("eval_only requires mode amp")
        if not checkpoint_artifact:
            raise EnqueueError("eval_only requires checkpoint_artifact")
    elif checkpoint_artifact:
        raise EnqueueError("checkpoint_artifact is only valid when eval_only is true")

    root = settings.resolved_platform_data_dir()
    job_id = str(uuid.uuid4())
    ws = job_workspace(root, user_id, job_id)
    ws.mkdir(parents=True, exist_ok=True)

    if reference_trajectory is not None:
        (ws / "reference_trajectory.json").write_text(
            json.dumps(reference_trajectory, indent=2),
            encoding="utf-8",
        )
    else:
        assert reference_artifact is not None
        name = validate_artifact_name(reference_artifact)
        src = user_artifacts_dir(root, user_id) / name
        src = src.resolve()
        base = user_artifacts_dir(root, user_id).resolve()
        if not str(src).startswith(str(base)) or not src.is_file():
            raise EnqueueError("reference_artifact not found or outside user artifact store")
        shutil.copy(src, ws / "reference_trajectory.json")

    if demonstration_dataset is not None:
        (ws / "demonstration_dataset.json").write_text(
            json.dumps(demonstration_dataset, indent=2),
            encoding="utf-8",
        )
    elif demonstration_artifact:
        name = validate_artifact_name(demonstration_artifact)
        src = user_artifacts_dir(root, user_id) / name
        src = src.resolve()
        base = user_artifacts_dir(root, user_id).resolve()
        if not str(src).startswith(str(base)) or not src.is_file():
            raise EnqueueError("demonstration_artifact not found or outside user artifact store")
        shutil.copy(src, ws / "demonstration_dataset.json")

    if eval_only:
        assert checkpoint_artifact is not None
        ck_name = validate_artifact_name(checkpoint_artifact)
        ck_src = user_artifacts_dir(root, user_id) / ck_name
        ck_src = ck_src.resolve()
        base = user_artifacts_dir(root, user_id).resolve()
        if not str(ck_src).startswith(str(base)) or not ck_src.is_file():
            raise EnqueueError("checkpoint_artifact not found or outside user artifact store")
        shutil.copy(ck_src, ws / POLICY_CHECKPOINT_WS_NAME)

    (ws / PLATFORM_MOTION_META_NAME).write_text(
        json.dumps(
            {"eval_only": bool(eval_only), "motion_export": motion_export or {}},
            indent=2,
        ),
        encoding="utf-8",
    )

    cfg = dict(config)
    cfg["output_dir"] = str((ws / "train_out").resolve())
    (ws / "train_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    rel = workspace_relpath(user_id, job_id)
    job_insert(
        settings.platform_sqlite_path(),
        job_id=job_id,
        user_id=user_id,
        status="queued",
        mode=mode,
        workspace_relpath=rel,
    )
    return job_id
