"""Tests for AMP eval-only job API and train subprocess wiring."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

TEST_FILE = Path(__file__).resolve()
BACKEND_ROOT = TEST_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.main import CreateTrainJobRequest  # noqa: E402
from app.platform_enqueue import (  # noqa: E402
    PLATFORM_MOTION_META_NAME,
    POLICY_CHECKPOINT_WS_NAME,
    enqueue_train_job,
)


def _minimal_reference() -> dict:
    return {
        "schema_version": "1.0.0",
        "robot_model": "g1_29dof",
        "units": {"angle": "radians", "time": "seconds"},
        "frequency_hz": 50.0,
        "root_model": "root_not_in_reference",
        "joint_order": ["0"],
        "joint_positions": [[0.0], [0.1]],
        "joint_velocities": [[0.0], [0.0]],
    }


def test_create_train_job_eval_only_validation() -> None:
    with pytest.raises(ValidationError, match="checkpoint_artifact"):
        CreateTrainJobRequest(
            mode="amp",
            eval_only=True,
            reference_trajectory=_minimal_reference(),
        )

    with pytest.raises(ValidationError, match="checkpoint_artifact"):
        CreateTrainJobRequest(
            mode="amp",
            eval_only=False,
            checkpoint_artifact="foo.zip",
            reference_trajectory=_minimal_reference(),
        )

    with pytest.raises(ValidationError, match="eval_only"):
        CreateTrainJobRequest(
            mode="train",
            eval_only=True,
            checkpoint_artifact="foo.zip",
            reference_trajectory=_minimal_reference(),
        )

    req = CreateTrainJobRequest(
        mode="amp",
        eval_only=True,
        checkpoint_artifact="policy.zip",
        reference_trajectory=_minimal_reference(),
        motion_export={"joint_map_version": "1.1"},
    )
    assert req.eval_only is True
    assert req.motion_export == {"joint_map_version": "1.1"}


def test_enqueue_eval_only_writes_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("G1_PLATFORM_DATA_DIR", str(tmp_path / "pdata"))

    def _noop_insert(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.platform_enqueue.job_insert", _noop_insert)

    settings = Settings()
    root = settings.resolved_platform_data_dir()
    uid = "u1"
    art = root / "users" / uid / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    ck = art / "policy.zip"
    ck.write_bytes(b"PK\x03\x04")

    jid = enqueue_train_job(
        settings,
        uid,
        config={"mode": "amp", "seed": 1, "env": {"mjcf_path": "/tmp/mjcf.xml"}},
        mode="amp",
        reference_trajectory=_minimal_reference(),
        reference_artifact=None,
        demonstration_dataset=None,
        demonstration_artifact=None,
        eval_only=True,
        checkpoint_artifact="policy.zip",
        motion_export={"k": "v"},
    )

    from app.platform_paths import job_workspace

    ws = job_workspace(root, uid, jid)
    assert (ws / POLICY_CHECKPOINT_WS_NAME).is_file()
    assert (ws / "reference_trajectory.json").is_file()
    meta = json.loads((ws / PLATFORM_MOTION_META_NAME).read_text(encoding="utf-8"))
    assert meta["eval_only"] is True
    assert meta["motion_export"] == {"k": "v"}


@pytest.mark.asyncio
async def test_run_train_eval_only_cmd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.services import pipeline

    captured: dict[str, list[str]] = {}

    async def _spy(argv: list[str], **kwargs: object) -> tuple[int, str, str]:
        captured["argv"] = argv
        return 0, "", ""

    monkeypatch.setattr(pipeline, "run_subprocess", _spy)

    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")
    ref = tmp_path / "ref.json"
    ref.write_text("{}", encoding="utf-8")
    ck = tmp_path / "p.zip"
    ck.write_bytes(b"x")
    ev = tmp_path / "out" / "eval_motion.json"

    await pipeline.run_train(
        Path("/sdk"),
        Path("/sf"),
        cfg,
        ref,
        None,
        mode="amp",
        eval_only=True,
        eval_checkpoint=ck,
        eval_output=ev,
    )
    argv = captured["argv"]
    assert "--eval-only" in argv
    assert "--checkpoint" in argv
    assert str(ck.resolve()) in argv
    assert "--eval-output" in argv
    assert str(ev.resolve()) in argv
