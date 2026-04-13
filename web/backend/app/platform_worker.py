"""Background worker: claim queued training jobs and run skill-foundry-train."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.platform_db import (
    job_count_running_for_user,
    job_finish,
    job_get,
    job_list_queued_ordered,
    job_try_claim,
)
from app.services.pipeline import run_train

logger = logging.getLogger(__name__)


def _pick_claimable_job_id(settings: Settings) -> str | None:
    db_path = settings.platform_sqlite_path()
    max_c = settings.max_concurrent_jobs_per_user
    for job_id, user_id in job_list_queued_ordered(db_path):
        if job_count_running_for_user(db_path, user_id) >= max_c:
            continue
        now = time.time()
        if job_try_claim(db_path, job_id, now):
            return job_id
    return None


async def _run_claimed_job(settings: Settings, job_id: str) -> None:
    db_path = settings.platform_sqlite_path()
    row = job_get(db_path, job_id)
    if not row or row["status"] != "running":
        return

    root = settings.resolved_platform_data_dir()
    workspace = root / row["workspace_relpath"]
    sdk = settings.resolved_sdk_root()
    sf = settings.resolved_skill_foundry_root()
    cfg_path = workspace / "train_config.json"
    ref_path = workspace / "reference_trajectory.json"
    demo_path = workspace / "demonstration_dataset.json"
    mode = str(row["mode"])
    timeout = max(1.0, float(settings.job_timeout_sec))

    if not cfg_path.is_file() or not ref_path.is_file():
        job_finish(
            db_path,
            job_id,
            status="failed",
            exit_code=2,
            error_message="missing train_config.json or reference_trajectory.json in workspace",
        )
        return

    eval_only = False
    pm = workspace / "platform_motion.json"
    if pm.is_file():
        import json

        try:
            meta = json.loads(pm.read_text(encoding="utf-8"))
            eval_only = bool(meta.get("eval_only"))
        except (json.JSONDecodeError, OSError):
            eval_only = False

    eval_kw: dict = {}
    if eval_only:
        ck = workspace / "policy_checkpoint.zip"
        eval_out = workspace / "train_out" / "eval_motion.json"
        eval_kw = {
            "eval_only": True,
            "eval_checkpoint": ck,
            "eval_output": eval_out,
        }

    out_log = workspace / "train_stdout.log"
    err_log = workspace / "train_stderr.log"

    try:
        result = await asyncio.wait_for(
            run_train(
                sdk,
                sf,
                cfg_path,
                ref_path,
                demo_path if demo_path.is_file() else None,
                mode=mode,
                **eval_kw,
            ),
            timeout=timeout,
        )
        out_log.write_text(result.get("stdout") or "", encoding="utf-8")
        err_log.write_text(result.get("stderr") or "", encoding="utf-8")
        code = int(result.get("exit_code") or 0)
        if code == 0:
            job_finish(db_path, job_id, status="succeeded", exit_code=0)
        else:
            job_finish(
                db_path,
                job_id,
                status="failed",
                exit_code=code,
                error_message=(result.get("stderr") or "")[:4000],
            )
    except TimeoutError:
        msg = f"job exceeded job_timeout_sec={timeout}"
        logger.warning("%s job_id=%s", msg, job_id)
        err_log.write_text(msg + "\n", encoding="utf-8")
        job_finish(db_path, job_id, status="failed", exit_code=-1, error_message=msg)
    except Exception as e:
        logger.exception("job %s", job_id)
        err_log.write_text(repr(e), encoding="utf-8")
        job_finish(db_path, job_id, status="failed", exit_code=-1, error_message=repr(e))


async def platform_worker_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    poll_sec = 0.75
    while not stop_event.is_set():
        try:
            jid = await asyncio.to_thread(_pick_claimable_job_id, settings)
            if jid:
                await _run_claimed_job(settings, jid)
            else:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_sec)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("platform worker loop")
            await asyncio.sleep(poll_sec)
