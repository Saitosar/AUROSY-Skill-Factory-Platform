"""Load and compare playback logs (reproducibility DoD)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def save_playback_log(path: Path | str, log: Any, *, compress: bool = True) -> None:
    """Persist PlaybackLog-like object with time_s, motor_q, motor_dq, ctrl, meta."""
    p = Path(path)
    meta = getattr(log, "meta", {})
    save_fn = np.savez_compressed if compress else np.savez
    motor_dq = getattr(log, "motor_dq", None)
    kwargs: dict[str, Any] = {
        "time_s": log.time_s,
        "motor_q": log.motor_q,
        "ctrl": log.ctrl,
        "meta_json": np.array(json.dumps(meta)),
    }
    if motor_dq is not None:
        kwargs["motor_dq"] = motor_dq
    save_fn(p, **kwargs)


def load_playback_log(path: Path | str) -> dict[str, Any]:
    """Load .npz written by save_playback_log."""
    data = np.load(Path(path), allow_pickle=True)
    meta: dict[str, Any] = {}
    if "meta_json" in data.files:
        meta = json.loads(str(data["meta_json"].item()))
    out: dict[str, Any] = {
        "time_s": np.asarray(data["time_s"]),
        "motor_q": np.asarray(data["motor_q"]),
        "ctrl": np.asarray(data["ctrl"]),
        "meta": meta,
    }
    if "motor_dq" in data.files:
        out["motor_dq"] = np.asarray(data["motor_dq"])
    else:
        out["motor_dq"] = None
    return out


def compare_playback_logs(
    a: dict[str, Any] | Any,
    b: dict[str, Any] | Any,
    *,
    atol: float = 1e-5,
    rtol: float = 1e-6,
) -> tuple[bool, list[str]]:
    """
    Compare two logs (dict from load_playback_log or PlaybackLog instances).

    Returns
    -------
    ok
        True if all arrays match within tolerance.
    messages
        Human-readable differences when ok is False.
    """
    def _arr(name: str, x: Any) -> np.ndarray:
        v = getattr(x, name, None) if not isinstance(x, dict) else x.get(name)
        if v is None:
            raise KeyError(name)
        return np.asarray(v)

    ta = _arr("time_s", a)
    tb = _arr("time_s", b)
    msgs: list[str] = []
    ok = True
    if ta.shape != tb.shape:
        ok = False
        msgs.append(f"time_s shape mismatch: {ta.shape} vs {tb.shape}")
    elif not np.allclose(ta, tb, atol=atol, rtol=rtol):
        ok = False
        msgs.append("time_s values differ beyond tolerance")

    for key in ("motor_q", "ctrl"):
        xa = _arr(key, a)
        xb = _arr(key, b)
        if xa.shape != xb.shape:
            ok = False
            msgs.append(f"{key} shape mismatch: {xa.shape} vs {xb.shape}")
        elif not np.allclose(xa, xb, atol=atol, rtol=rtol):
            diff = float(np.max(np.abs(xa - xb)))
            ok = False
            msgs.append(f"{key} max abs diff: {diff}")

    def _optional_arr(name: str, x: Any) -> np.ndarray | None:
        if isinstance(x, dict):
            v = x.get(name)
        else:
            v = getattr(x, name, None)
        if v is None:
            return None
        return np.asarray(v)

    da = _optional_arr("motor_dq", a)
    db = _optional_arr("motor_dq", b)
    if da is not None and db is not None:
        if da.shape != db.shape:
            ok = False
            msgs.append(f"motor_dq shape mismatch: {da.shape} vs {db.shape}")
        elif not np.allclose(da, db, atol=atol, rtol=rtol):
            diff = float(np.max(np.abs(da - db)))
            ok = False
            msgs.append(f"motor_dq max abs diff: {diff}")
    elif da is not None or db is not None:
        ok = False
        msgs.append("motor_dq present in only one log")

    return ok, msgs
