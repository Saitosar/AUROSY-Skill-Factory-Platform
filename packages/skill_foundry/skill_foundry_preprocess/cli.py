"""CLI for preprocessing landmarks into AUROSY canonical format."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .converter import preprocess_landmarks_payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preprocess motion landmarks")
    parser.add_argument("input", type=Path, help="Input JSON with landmarks")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output JSON path")
    parser.add_argument(
        "--filter",
        dest="filter_type",
        choices=("savgol", "kalman", "both"),
        default="both",
        help="Filtering strategy",
    )
    parser.add_argument("--window", dest="window_length", type=int, default=7)
    parser.add_argument("--polyorder", type=int, default=2)
    parser.add_argument("--confidence-threshold", type=float, default=0.3)
    parser.add_argument("--process-noise", type=float, default=0.01)
    parser.add_argument("--measurement-noise", type=float, default=0.1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = preprocess_landmarks_payload(
        payload,
        filter_type=args.filter_type,
        window_length=args.window_length,
        polyorder=args.polyorder,
        confidence_threshold=args.confidence_threshold,
        process_noise=args.process_noise,
        measurement_noise=args.measurement_noise,
    )
    result.save_json(args.output)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

