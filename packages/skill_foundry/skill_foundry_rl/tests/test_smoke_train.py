"""Smoke train determinism on golden reference."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_foundry_rl.smoke_train import run_smoke_train

_GOLDEN = Path(__file__).resolve().parents[4] / "docs" / "skill_foundry" / "golden" / "v1"


@pytest.mark.skipif(not _GOLDEN.is_dir(), reason="golden fixtures not in tree")
def test_smoke_train_reproducible_losses() -> None:
    pytest.importorskip("torch")
    ref = _GOLDEN / "reference_trajectory.json"
    if not ref.is_file():
        pytest.skip("reference_trajectory.json missing")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        cfg = {"seed": 42, "smoke_steps": 5, "learning_rate": 0.01}
        p1 = run_smoke_train(reference_path=ref, demonstration_path=None, config=cfg, output_dir=out / "a")
        p2 = run_smoke_train(reference_path=ref, demonstration_path=None, config=cfg, output_dir=out / "b")
        assert p1["losses"] == p2["losses"]
        assert p1["final_loss"] == p2["final_loss"]
        assert (out / "a" / "train_run.json").is_file()
        body = json.loads((out / "a" / "train_run.json").read_text(encoding="utf-8"))
        assert body["status"] == "ok"
