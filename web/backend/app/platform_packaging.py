"""Run skill-foundry-package pack for Phase 5 distribution."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.services.pipeline import python_m_cmd, run_subprocess
from app.services.sdk_path import combined_pythonpath


async def run_package_pack(
    sdk_root: Path,
    skill_foundry_root: Path,
    *,
    train_config: Path,
    reference_trajectory: Path,
    run_dir: Path,
    output_archive: Path,
) -> dict[str, Any]:
    bin_pk = shutil.which("skill-foundry-package")
    if bin_pk:
        cmd = [
            bin_pk,
            "pack",
            "--train-config",
            str(train_config.resolve()),
            "--reference-trajectory",
            str(reference_trajectory.resolve()),
            "--run-dir",
            str(run_dir.resolve()),
            "--output",
            str(output_archive.resolve()),
        ]
    else:
        cmd = python_m_cmd("skill_foundry_export.cli")
        cmd.extend(
            [
                "pack",
                "--train-config",
                str(train_config.resolve()),
                "--reference-trajectory",
                str(reference_trajectory.resolve()),
                "--run-dir",
                str(run_dir.resolve()),
                "--output",
                str(output_archive.resolve()),
            ]
        )
    env = {"PYTHONPATH": combined_pythonpath(skill_foundry_root, sdk_root)}
    code, out, err = await run_subprocess(cmd, env=env)
    return {"exit_code": code, "stdout": out, "stderr": err}
