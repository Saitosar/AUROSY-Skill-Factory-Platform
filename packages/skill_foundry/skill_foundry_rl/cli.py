"""CLI: Phase 3.1 smoke train or Phase 3.2/3.3 PPO train — ReferenceTrajectory (+ optional DemonstrationDataset)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise SystemExit(
                "PyYAML is required for .yaml/.yml configs. "
                "Install pyyaml or use a .json config."
            ) from exc
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("config must be a mapping at the top level")
        return data
    if suffix == ".json":
        raw = json.loads(text)
        if not isinstance(raw, dict):
            raise ValueError("config must be a JSON object at the top level")
        return raw
    raise ValueError(f"unsupported config extension: {suffix} (use .json, .yaml, .yml)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill-foundry-train",
        description=(
            "Skill Foundry RL worker: Phase 3.1 smoke train (default) or Phase 3.2 PPO "
            "(MuJoCo G1TrackingEnv)."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("smoke", "train"),
        default="smoke",
        help="smoke: Phase 3.1 contract + tiny torch loop; train: Phase 3.2 PPO on G1TrackingEnv.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Training config (.json or .yaml): seed, output_dir, mode-specific keys.",
    )
    parser.add_argument(
        "--reference-trajectory",
        type=Path,
        required=True,
        help="Path to reference_trajectory.json (ReferenceTrajectory v1).",
    )
    parser.add_argument(
        "--demonstration-dataset",
        type=Path,
        default=None,
        help=(
            "Optional DemonstrationDataset v1 JSON. Smoke mode: validated and hashed. "
            "Train mode: used for Phase 3.3 BC when bc.enabled is true (overrides bc.demonstration_dataset)."
        ),
    )
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)
    out = Path(cfg.get("output_dir", "./skill_foundry_runs/smoke"))
    if not out.is_absolute():
        out = (args.config.resolve().parent / out).resolve()

    ref_path = args.reference_trajectory
    demo_path = args.demonstration_dataset

    mode = str(cfg.get("mode", args.mode))
    if mode not in ("smoke", "train"):
        mode = args.mode

    if mode == "train":
        try:
            from skill_foundry_rl.ppo_train import run_ppo_train
        except ImportError as exc:
            print(
                "Missing RL training dependencies. Install with: pip install -e '.[rl]'",
                file=sys.stderr,
            )
            raise
        payload = run_ppo_train(
            reference_path=ref_path,
            config=cfg,
            output_dir=out,
            demonstration_path=demo_path,
        )
        print(json.dumps(payload, indent=2))
        return 0

    try:
        from skill_foundry_rl.smoke_train import run_smoke_train
    except ImportError as exc:
        if "torch" in str(exc).lower():
            print(
                "Missing RL dependencies. Install with: pip install -e '.[rl]'",
                file=sys.stderr,
            )
        raise

    payload = run_smoke_train(
        reference_path=ref_path,
        demonstration_path=demo_path,
        config=cfg,
        output_dir=out,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
