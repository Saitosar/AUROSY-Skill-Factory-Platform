from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from skill_foundry_rl.cli import main


def test_cli_amp_mode_dispatch(monkeypatch, tmp_path: Path, capsys) -> None:
    cfg = {"mode": "amp", "output_dir": "out", "env": {"mjcf_path": "/tmp/x.xml"}}
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    ref_path = tmp_path / "reference.json"
    ref_path.write_text(json.dumps({"dummy": True}), encoding="utf-8")

    fake_mod = types.ModuleType("skill_foundry_rl.amp_train")

    def _run_amp_train(*, reference_path: Path, config: dict, output_dir: Path, demonstration_path: Path | None):
        assert reference_path == ref_path
        assert config["mode"] == "amp"
        assert output_dir == (cfg_path.resolve().parent / "out").resolve()
        assert demonstration_path is None
        return {"status": "ok", "phase": "4_amp"}

    fake_mod.run_amp_train = _run_amp_train  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "skill_foundry_rl.amp_train", fake_mod)

    rc = main(
        [
            "--mode",
            "amp",
            "--config",
            str(cfg_path),
            "--reference-trajectory",
            str(ref_path),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert '"phase": "4_amp"' in out


def test_cli_eval_only_requires_checkpoint(tmp_path: Path, capsys) -> None:
    cfg = {"mode": "amp", "output_dir": "out", "env": {"mjcf_path": "/tmp/x.xml"}}
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    ref_path = tmp_path / "reference.json"
    ref_path.write_text("{}", encoding="utf-8")
    rc = main(
        [
            "--mode",
            "amp",
            "--eval-only",
            "--config",
            str(cfg_path),
            "--reference-trajectory",
            str(ref_path),
        ]
    )
    assert rc == 2
    assert "checkpoint" in capsys.readouterr().err.lower()


def test_cli_eval_only_dispatch(monkeypatch, tmp_path: Path, capsys) -> None:
    cfg = {"mode": "amp", "output_dir": "out", "env": {"mjcf_path": "/tmp/x.xml"}}
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    ref_path = tmp_path / "reference.json"
    ref_path.write_text("{}", encoding="utf-8")
    ck = tmp_path / "policy.zip"
    ck.write_bytes(b"x")

    fake_mod = types.ModuleType("skill_foundry_rl.motion_eval")

    def _run_amp_eval(**kwargs):
        assert kwargs["checkpoint_path"] == ck.resolve()
        return {"schema_version": "1.0", "rollout_steps": 3}

    fake_mod.run_amp_eval = _run_amp_eval  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "skill_foundry_rl.motion_eval", fake_mod)

    rc = main(
        [
            "--mode",
            "amp",
            "--eval-only",
            "--config",
            str(cfg_path),
            "--reference-trajectory",
            str(ref_path),
            "--checkpoint",
            str(ck),
        ]
    )
    assert rc == 0
    assert "eval_motion" in capsys.readouterr().out
