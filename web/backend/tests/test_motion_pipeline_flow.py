"""Phase 6 motion pipeline orchestration (state + idempotency)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

TEST_FILE = Path(__file__).resolve()
BACKEND_ROOT = TEST_FILE.parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
SF_PKG = REPO_ROOT / "packages" / "skill_foundry"
for p in (BACKEND_ROOT, SF_PKG):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.config import Settings  # noqa: E402
from app.services.motion_pipeline import (  # noqa: E402
    MotionPipelineError,
    get_motion_pipeline_state,
    load_state,
    run_motion_pipeline_action,
    save_state,
)


def _full_reference() -> dict:
    return {
        "schema_version": "1.0.0",
        "robot_model": "g1_29dof",
        "units": {"angle": "radians", "time": "seconds"},
        "frequency_hz": 50.0,
        "root_model": "root_not_in_reference",
        "joint_order": [str(i) for i in range(29)],
        "joint_positions": [[0.01 * i for i in range(29)], [0.02 * i for i in range(29)]],
        "joint_velocities": [[0.0] * 29, [0.0] * 29],
    }


@pytest.mark.asyncio
async def test_motion_pipeline_init_and_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("G1_PLATFORM_DATA_DIR", str(tmp_path / "pdata"))
    s = Settings()
    uid = "u1"
    pid = "run-001"
    r = await run_motion_pipeline_action(s, uid, pipeline_id=pid, action="init")
    assert r["ok"] and r["pipeline_id"] == pid
    st = get_motion_pipeline_state(s, uid, pid)
    assert st["state"]["stages"]["capture"]["status"] == "pending"


@pytest.mark.asyncio
async def test_build_reference_from_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("G1_PLATFORM_DATA_DIR", str(tmp_path / "pdata"))
    s = Settings()
    root = s.resolved_platform_data_dir()
    uid = "u1"
    pid = "run-002"
    art = root / "users" / uid / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "ref.json").write_text(json.dumps(_full_reference()), encoding="utf-8")

    await run_motion_pipeline_action(s, uid, pipeline_id=pid, action="init")
    await run_motion_pipeline_action(
        s,
        uid,
        pipeline_id=pid,
        action="build_reference",
        reference_artifact="ref.json",
    )
    st = get_motion_pipeline_state(s, uid, pid)
    assert st["state"]["stages"]["reference"]["status"] == "done"


@pytest.mark.asyncio
async def test_enqueue_train_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("G1_PLATFORM_DATA_DIR", str(tmp_path / "pdata"))
    calls: list[str] = []

    def _fake_enqueue(settings: Settings, user_id: str, **kwargs: object) -> str:
        calls.append("enqueue")
        return "job-fixed-id"

    def _fake_job_get(_db: object, job_id: str) -> dict:
        return {
            "id": job_id,
            "status": "queued",
            "mode": "smoke",
            "workspace_relpath": "users/u1/jobs/job-fixed-id",
        }

    monkeypatch.setattr("app.services.motion_pipeline.enqueue_train_job", _fake_enqueue)
    monkeypatch.setattr("app.services.motion_pipeline.job_get", _fake_job_get)
    monkeypatch.setattr(
        "app.services.motion_pipeline._run_pretraining_validation",
        lambda _ref: {"passed": True, "failure_reasons": []},
    )

    s = Settings()
    root = s.resolved_platform_data_dir()
    uid = "u1"
    pid = "run-003"
    art = root / "users" / uid / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "ref.json").write_text(json.dumps(_full_reference()), encoding="utf-8")

    await run_motion_pipeline_action(s, uid, pipeline_id=pid, action="init")
    await run_motion_pipeline_action(
        s,
        uid,
        pipeline_id=pid,
        action="build_reference",
        reference_artifact="ref.json",
    )
    r1 = await run_motion_pipeline_action(
        s,
        uid,
        pipeline_id=pid,
        action="enqueue_train",
        train_config={"env": {"mjcf_path": str(REPO_ROOT / "packages" / "skill_foundry" / "skill_foundry_export" / "tests" / "fixtures" / "dummy_scene.xml")}},
        train_mode="smoke",
    )
    r2 = await run_motion_pipeline_action(
        s,
        uid,
        pipeline_id=pid,
        action="enqueue_train",
        train_config={},
        train_mode="smoke",
    )
    assert r1.get("job_id") == "job-fixed-id"
    assert r2.get("idempotent") is True
    assert len(calls) == 1


def test_unknown_pipeline_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("G1_PLATFORM_DATA_DIR", str(tmp_path / "pdata"))
    s = Settings()
    with pytest.raises(MotionPipelineError):
        get_motion_pipeline_state(s, "u1", "missing")


@pytest.mark.asyncio
async def test_build_reference_from_bvh_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("G1_PLATFORM_DATA_DIR", str(tmp_path / "pdata"))
    s = Settings()
    root = s.resolved_platform_data_dir()
    uid = "u1"
    pid = "run-004"
    art = root / "users" / uid / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "capture.bvh").write_text(
        "\n".join(
            [
                "HIERARCHY",
                "ROOT Hips",
                "{",
                "  OFFSET 0.0 0.0 0.0",
                "  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation",
                "  End Site",
                "  {",
                "    OFFSET 0.0 10.0 0.0",
                "  }",
                "}",
                "MOTION",
                "Frames: 2",
                "Frame Time: 0.033333",
                "0.0 0.0 0.0 0.0 0.0 0.0",
                "1.0 0.0 0.0 0.0 0.0 0.0",
            ]
        ),
        encoding="utf-8",
    )

    class _FakeRetargetResult:
        def __init__(self) -> None:
            self.joint_angles_rad = np.zeros((2, 29), dtype=np.float32)

    def _fake_run_retargeting(**kwargs: object) -> _FakeRetargetResult:
        frames = kwargs.get("frames")
        assert isinstance(frames, np.ndarray)
        assert frames.shape == (2, 33, 3)
        return _FakeRetargetResult()

    monkeypatch.setattr("app.services.motion_pipeline.run_retargeting", _fake_run_retargeting)

    await run_motion_pipeline_action(s, uid, pipeline_id=pid, action="init")
    await run_motion_pipeline_action(
        s,
        uid,
        pipeline_id=pid,
        action="build_reference",
        bvh_artifact="capture.bvh",
    )
    st = get_motion_pipeline_state(s, uid, pid)
    assert st["state"]["stages"]["reference"]["status"] == "done"


@pytest.mark.asyncio
async def test_preprocess_stage_runs_before_build_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("G1_PLATFORM_DATA_DIR", str(tmp_path / "pdata"))
    s = Settings()
    root = s.resolved_platform_data_dir()
    uid = "u1"
    pid = "run-005"
    art = root / "users" / uid / "artifacts"
    art.mkdir(parents=True, exist_ok=True)

    n = 20
    landmarks = np.zeros((n, 33, 3), dtype=np.float32)
    for i in range(n):
        landmarks[i, :, 0] = i * 0.01
        landmarks[i, :, 1] = np.sin(i * 0.1)
        landmarks[i, :, 2] = np.cos(i * 0.1)
    (art / "landmarks.json").write_text(
        json.dumps(
            {
                "schema_version": "aurosy_video_landmarks_v1",
                "landmarks": landmarks.tolist(),
                "confidences": [1.0] * n,
                "timestamps_ms": (np.arange(n, dtype=np.float32) * 33.33).tolist(),
            }
        ),
        encoding="utf-8",
    )

    class _FakeRetargetResult:
        def __init__(self) -> None:
            self.joint_angles_rad = np.zeros((n, 29), dtype=np.float32)

    monkeypatch.setattr(
        "app.services.motion_pipeline.run_retargeting",
        lambda **kwargs: _FakeRetargetResult(),
    )

    await run_motion_pipeline_action(s, uid, pipeline_id=pid, action="init")
    await run_motion_pipeline_action(
        s,
        uid,
        pipeline_id=pid,
        action="build_reference",
        landmarks_artifact="landmarks.json",
    )
    st = get_motion_pipeline_state(s, uid, pid)["state"]
    assert st["stages"]["preprocess"]["status"] == "done"
    assert isinstance(st.get("preprocessed_artifact"), str)
    assert st["stages"]["reference"]["status"] == "done"


@pytest.mark.asyncio
async def test_preprocess_motion_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("G1_PLATFORM_DATA_DIR", str(tmp_path / "pdata"))
    s = Settings()
    root = s.resolved_platform_data_dir()
    uid = "u1"
    pid = "run-006"
    art = root / "users" / uid / "artifacts"
    art.mkdir(parents=True, exist_ok=True)

    (art / "capture.json").write_text(
        json.dumps(
            {
                "schema_version": "aurosy_video_landmarks_v1",
                "landmarks": np.zeros((5, 33, 3), dtype=np.float32).tolist(),
                "confidences": [1.0] * 5,
                "timestamps_ms": [0, 33, 66, 99, 132],
            }
        ),
        encoding="utf-8",
    )

    await run_motion_pipeline_action(s, uid, pipeline_id=pid, action="init")
    state = load_state(root, uid, pid)
    assert state is not None
    state["capture_artifact"] = "capture.json"
    state["stages"]["pose_extract"]["status"] = "done"
    save_state(root, uid, pid, state)

    result = await run_motion_pipeline_action(
        s,
        uid,
        pipeline_id=pid,
        action="preprocess_motion",
        capture_artifact="capture.json",
    )
    assert result["ok"] is True
    out_state = result["state"]
    assert out_state["stages"]["preprocess"]["status"] == "done"
    assert isinstance(out_state.get("preprocessed_artifact"), str)
