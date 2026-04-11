"""CLI: Phase 6.1 product validation (N-episode tracking MSE + falls)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_train_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        raise SystemExit(f"unsupported config extension: {suffix}")
    if not isinstance(data, dict):
        raise SystemExit("train config must be a mapping")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill-foundry-validate",
        description="Run product validation (tracking MSE + fall count) on a PPO checkpoint.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Training config (.json/.yaml) used for env settings (must match training).",
    )
    parser.add_argument(
        "--reference-trajectory",
        type=Path,
        required=True,
        help="ReferenceTrajectory v1 JSON (same as training).",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="PPO .zip checkpoint (default: <run-dir>/ppo_G1TrackingEnv.zip if --run-dir set).",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Training output directory containing ppo_G1TrackingEnv.zip (optional if --checkpoint set).",
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=None,
        help="Thresholds YAML/JSON (default: bundled validation_thresholds.default.yaml).",
    )
    parser.add_argument(
        "--n-episodes",
        type=int,
        default=None,
        help="Override number of eval episodes (default: from thresholds file).",
    )
    parser.add_argument(
        "--val-seed",
        type=int,
        default=None,
        help="Base seed for episode resets (default: train early_stop.val_seed or seed+1).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write validation_report.json to this path (default: stdout only if not set).",
    )
    args = parser.parse_args(argv)

    try:
        from skill_foundry_rl.product_validation import (
            run_product_validation_safe,
            write_validation_report_json,
        )
    except ImportError as exc:
        print("Missing RL dependencies. Install with: pip install -e '.[rl]'", file=sys.stderr)
        raise SystemExit(1) from exc

    cfg = _load_train_config(args.config.resolve())
    ref = args.reference_trajectory.expanduser().resolve()

    ckpt = args.checkpoint
    if ckpt is None:
        if args.run_dir is None:
            print("Either --checkpoint or --run-dir is required.", file=sys.stderr)
            return 2
        rd = args.run_dir.expanduser().resolve()
        ckpt = rd / "ppo_G1TrackingEnv.zip"
    else:
        ckpt = ckpt.expanduser().resolve()

    if not ckpt.is_file():
        print(f"Checkpoint not found: {ckpt}", file=sys.stderr)
        return 2

    th_path = args.thresholds.expanduser().resolve() if args.thresholds else None

    seed = int(cfg.get("seed", 42))
    early = cfg.get("early_stop") or {}
    val_seed = int(args.val_seed if args.val_seed is not None else early.get("val_seed", seed + 1))

    overrides = {"n_episodes": int(args.n_episodes)} if args.n_episodes is not None else None

    report = run_product_validation_safe(
        checkpoint_path=ckpt,
        reference_path=ref,
        train_config=cfg,
        thresholds_path=th_path,
        val_seed=val_seed,
        threshold_overrides=overrides,
    )

    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        write_validation_report_json(args.output.expanduser().resolve(), report)
    print(text)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
