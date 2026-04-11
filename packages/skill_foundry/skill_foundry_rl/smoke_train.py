"""
Deterministic smoke training for Phase 3.1 DoD: validates contracts, runs a tiny torch loop.
Full MuJoCo PPO is Phase 3.2.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from skill_foundry_phase0.contract_validator import (
    validate_demonstration_dataset_dict,
    validate_reference_trajectory_dict,
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_reference_tensor(ref: dict[str, Any], max_elements: int = 512) -> torch.Tensor:
    positions = ref["joint_positions"]
    arr = np.asarray(positions, dtype=np.float32).reshape(-1)
    if arr.size > max_elements:
        arr = arr[:max_elements]
    return torch.from_numpy(arr.copy())


def _demo_summary_tensor(demo: dict[str, Any] | None, max_elements: int = 256) -> torch.Tensor | None:
    if demo is None:
        return None
    episodes = demo.get("episodes") or []
    if not episodes:
        return None
    steps = episodes[0].get("steps") or []
    if not steps:
        return None
    obs = steps[0].get("obs")
    if not isinstance(obs, list):
        return None
    arr = np.asarray(obs[:max_elements], dtype=np.float32)
    return torch.from_numpy(arr.copy())


def run_smoke_train(
    *,
    reference_path: Path,
    demonstration_path: Path | None,
    config: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """
    Load and validate Phase 0.2 JSON, then run a short reproducible optimization on CPU
    (stable floats for DoD; full RL may use GPU in later phases).
    """
    ref_raw = _load_json(reference_path)
    ref_errors = validate_reference_trajectory_dict(ref_raw)
    if ref_errors:
        raise ValueError("Invalid reference_trajectory.json:\n" + "\n".join(ref_errors))

    demo_raw: dict[str, Any] | None = None
    if demonstration_path is not None:
        demo_raw = _load_json(demonstration_path)
        demo_errors = validate_demonstration_dataset_dict(demo_raw)
        if demo_errors:
            raise ValueError("Invalid demonstration_dataset.json:\n" + "\n".join(demo_errors))

    seed = int(config.get("seed", 42))
    smoke_steps = int(config.get("smoke_steps", 5))
    lr = float(config.get("learning_rate", 0.01))

    torch.manual_seed(seed)
    np.random.seed(seed & 0xFFFFFFFF)

    device = torch.device("cpu")
    x = _flatten_reference_tensor(ref_raw).to(device)
    d_in = x.numel()
    if d_in == 0:
        raise ValueError("reference joint_positions produced empty tensor")

    demo_vec = _demo_summary_tensor(demo_raw)
    if demo_vec is not None:
        # Concatenate normalized demo obs tail for slightly richer input
        if demo_vec.numel() > d_in:
            demo_vec = demo_vec[:d_in]
        elif demo_vec.numel() < d_in:
            pad = torch.zeros(d_in - demo_vec.numel(), dtype=demo_vec.dtype, device=device)
            demo_vec = torch.cat([demo_vec.to(device), pad], dim=0)
        else:
            demo_vec = demo_vec.to(device)
        x = 0.5 * x + 0.5 * demo_vec

    model = nn.Linear(d_in, 1, bias=True).to(device)
    for p in model.parameters():
        nn.init.normal_(p, mean=0.0, std=0.02)

    optim = torch.optim.Adam(model.parameters(), lr=lr)
    losses: list[float] = []
    for _ in range(smoke_steps):
        pred = model(x)
        target = torch.zeros_like(pred)
        loss = nn.functional.mse_loss(pred, target)
        optim.zero_grad()
        loss.backward()
        optim.step()
        losses.append(float(loss.item()))

    output_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = output_dir / "smoke_checkpoint.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "meta": {
                "phase": "3.1_smoke",
                "reference_path": str(reference_path),
                "demonstration_path": str(demonstration_path) if demonstration_path else None,
                "seed": seed,
                "smoke_steps": smoke_steps,
            },
        },
        ckpt_path,
    )

    payload = {
        "status": "ok",
        "seed": seed,
        "smoke_steps": smoke_steps,
        "losses": losses,
        "final_loss": losses[-1] if losses else None,
        "reference_sha256": _sha256_file(reference_path),
        "checkpoint": str(ckpt_path),
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
    }
    if demonstration_path is not None:
        payload["demonstration_sha256"] = _sha256_file(demonstration_path)

    run_json = output_dir / "train_run.json"
    run_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
