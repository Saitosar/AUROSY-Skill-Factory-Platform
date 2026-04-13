"""Run Skill Foundry CLI tools as subprocesses."""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.services.sdk_path import combined_pythonpath

_MAX_NPZ_B64_BYTES = 8 * 1024 * 1024


async def run_subprocess(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **(env or {})},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    out = out_b.decode(errors="replace")
    err = err_b.decode(errors="replace")
    code = proc.returncode or 0
    return code, out, err


def which_skill_foundry() -> dict[str, str | None]:
    return {
        "preprocess": shutil.which("skill-foundry-preprocess"),
        "playback": shutil.which("skill-foundry-playback"),
        "train": shutil.which("skill-foundry-train"),
    }


def python_m_cmd(module: str) -> list[str]:
    return [sys.executable, "-m", module]


async def run_preprocess(
    sdk_root: Path,
    skill_foundry_root: Path,
    keyframes_json: dict[str, Any],
    frequency_hz: float | None = None,
    *,
    validate_motion: bool = True,
    mjcf_path: str | None = None,
) -> dict[str, Any]:
    """Write keyframes to temp file, run preprocess, return outputs + log."""
    with tempfile.TemporaryDirectory(prefix="g1_preprocess_") as td:
        root = Path(td)
        kf_path = root / "keyframes.json"
        kf_path.write_text(__import__("json").dumps(keyframes_json, indent=2), encoding="utf-8")
        out_path = root / "reference_trajectory.json"
        log_path = root / "preprocess_run.json"

        bin_pre = shutil.which("skill-foundry-preprocess")
        if bin_pre:
            cmd = [bin_pre, str(kf_path), "-o", str(out_path)]
        else:
            cmd = python_m_cmd("skill_foundry_preprocessing")
            cmd.extend([str(kf_path), "-o", str(out_path)])

        if frequency_hz is not None:
            cmd.extend(["--frequency-hz", str(frequency_hz)])

        env = {"PYTHONPATH": combined_pythonpath(skill_foundry_root, sdk_root)}
        code, out, err = await run_subprocess(cmd, cwd=root, env=env)

        ref_text = ""
        log_text = ""
        if out_path.is_file():
            ref_text = out_path.read_text(encoding="utf-8")
        if log_path.is_file():
            log_text = log_path.read_text(encoding="utf-8")

        out_payload: dict[str, Any] = {
            "exit_code": code,
            "stdout": out,
            "stderr": err,
            "reference_trajectory_json": ref_text if ref_text else None,
            "preprocess_run_json": log_text if log_text else None,
            "output_dir": str(root),
        }

        if validate_motion and code == 0 and ref_text:
            import json as _json

            from app.services.motion_validation import run_motion_validation

            try:
                ref_obj = _json.loads(ref_text)
                out_payload["motion_validation"] = run_motion_validation(
                    sdk_root,
                    skill_foundry_root,
                    ref_obj,
                    mjcf_path,
                    validate_motion=True,
                )
            except Exception as exc:  # noqa: BLE001
                out_payload["motion_validation"] = {
                    "ok": False,
                    "error": str(exc),
                }

        return out_payload


async def run_playback(
    sdk_root: Path,
    skill_foundry_root: Path,
    reference_path: Path,
    mjcf_path: Path,
    *,
    mode: str = "dynamic",
    dt: float = 0.005,
    kp: float = 150.0,
    kd: float = 5.0,
    seed: int = 0,
    max_steps: int | None = None,
    demonstration_json: bool = False,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="g1_pb_") as td:
        out_npz = Path(td) / "playback.npz"
        demo_path = Path(td) / "demonstration_dataset.json" if demonstration_json else None

        bin_pb = shutil.which("skill-foundry-playback")
        if bin_pb:
            cmd: list[str] = [
                bin_pb,
                str(reference_path.resolve()),
                "--mjcf",
                str(mjcf_path.resolve()),
                "--mode",
                mode,
                "--dt",
                str(dt),
                "--kp",
                str(kp),
                "--kd",
                str(kd),
                "--seed",
                str(seed),
                "-o",
                str(out_npz),
            ]
        else:
            cmd = python_m_cmd("skill_foundry_sim.cli")
            cmd.extend(
                [
                    str(reference_path.resolve()),
                    "--mjcf",
                    str(mjcf_path.resolve()),
                    "--mode",
                    mode,
                    "--dt",
                    str(dt),
                    "--kp",
                    str(kp),
                    "--kd",
                    str(kd),
                    "--seed",
                    str(seed),
                    "-o",
                    str(out_npz),
                ]
            )
        if max_steps is not None:
            cmd.extend(["--max-steps", str(max_steps)])
        if demonstration_json and demo_path is not None:
            cmd.extend(["--demonstration-json", str(demo_path)])

        env = {"PYTHONPATH": combined_pythonpath(skill_foundry_root, sdk_root)}
        code, out, err = await run_subprocess(cmd, env=env)

        demo_text = None
        if demo_path and demo_path.is_file():
            demo_text = demo_path.read_text(encoding="utf-8")

        npz_b64: str | None = None
        npz_size: int | None = None
        npz_omitted = False
        if out_npz.is_file():
            raw = out_npz.read_bytes()
            npz_size = len(raw)
            if len(raw) <= _MAX_NPZ_B64_BYTES:
                npz_b64 = base64.standard_b64encode(raw).decode("ascii")
            else:
                npz_omitted = True

        return {
            "exit_code": code,
            "stdout": out,
            "stderr": err,
            "output_npz_size_bytes": npz_size,
            "output_npz_base64": npz_b64,
            "output_npz_omitted_too_large": npz_omitted,
            "demonstration_dataset_json": demo_text,
        }


async def run_train(
    sdk_root: Path,
    skill_foundry_root: Path,
    config_path: Path,
    reference_path: Path,
    demonstration_path: Path | None = None,
    *,
    mode: str = "smoke",
    eval_only: bool = False,
    eval_checkpoint: Path | None = None,
    eval_output: Path | None = None,
) -> dict[str, Any]:
    bin_tr = shutil.which("skill-foundry-train")
    if bin_tr:
        cmd = [
            bin_tr,
            "--mode",
            mode,
            "--config",
            str(config_path.resolve()),
            "--reference-trajectory",
            str(reference_path.resolve()),
        ]
    else:
        cmd = python_m_cmd("skill_foundry_rl")
        cmd.extend(
            [
                "--mode",
                mode,
                "--config",
                str(config_path.resolve()),
                "--reference-trajectory",
                str(reference_path.resolve()),
            ]
        )
    if demonstration_path is not None:
        cmd.extend(["--demonstration-dataset", str(demonstration_path.resolve())])

    if eval_only:
        if eval_checkpoint is None or not eval_checkpoint.is_file():
            raise FileNotFoundError(
                "eval_only requires eval_checkpoint path to an existing policy zip"
            )
        if eval_output is None:
            raise ValueError("eval_only requires eval_output path for eval_motion.json")
        eval_output.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(
            [
                "--eval-only",
                "--checkpoint",
                str(eval_checkpoint.resolve()),
                "--eval-output",
                str(eval_output.resolve()),
            ]
        )

    env = {"PYTHONPATH": combined_pythonpath(skill_foundry_root, sdk_root)}
    code, out, err = await run_subprocess(cmd, env=env)
    return {"exit_code": code, "stdout": out, "stderr": err}
