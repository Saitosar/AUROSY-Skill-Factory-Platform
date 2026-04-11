"""Phase 6.1 product validation: tracking MSE and fall count over N deterministic episodes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from skill_foundry_phase0.contract_validator import validate_reference_trajectory_dict
from skill_foundry_sim.reference_loader import load_reference_trajectory_json

from skill_foundry_rl.g1_tracking_env import G1TrackingEnv, g1_env_cfg_from_train_config

VALIDATION_REPORT_SCHEMA_REF = "skill_foundry_product_validation_report_v1"
DEFAULT_THRESHOLDS_REL = "validation_thresholds.default.yaml"


def default_thresholds_path() -> Path:
    return Path(__file__).resolve().parent / DEFAULT_THRESHOLDS_REL


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_thresholds_file(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml  # type: ignore[import-untyped]

        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("thresholds file must be a mapping")
    return raw


def normalize_thresholds(raw: dict[str, Any]) -> dict[str, Any]:
    """Return validated threshold dict with required keys."""
    out = dict(raw)
    out.setdefault("schema_version", "1.0.0")
    out.setdefault("profile", "default")
    out["n_episodes"] = int(out.get("n_episodes", 10))
    out["max_mean_mse"] = float(out["max_mean_mse"])
    out["max_fall_episodes"] = int(out["max_fall_episodes"])
    if out["n_episodes"] < 1:
        raise ValueError("n_episodes must be >= 1")
    return out


def evaluate_policy_tracking_metrics(
    model: Any,
    env: G1TrackingEnv,
    *,
    n_episodes: int,
    base_seed: int,
    deterministic: bool = True,
) -> dict[str, Any]:
    """
    Roll out ``n_episodes`` episodes; aggregate:

    - ``mean_tracking_error_mse``: mean of ``info[\"mse_tracking\"]`` over all steps.
    - ``fall_episodes``: episodes where termination was due to fall (``fallen``).
    """
    total_mse = 0.0
    total_steps = 0
    fall_episodes = 0
    per_episode_mean_mse: list[float] = []

    for ep in range(n_episodes):
        obs, _ = env.reset(seed=int(base_seed + ep))
        ep_mse_sum = 0.0
        ep_steps = 0
        terminated = False
        truncated = False
        episode_fell = False

        while not (terminated or truncated):
            action, _ = model.predict(obs, deterministic=deterministic)
            obs, _reward, terminated, truncated, info = env.step(action)
            mse = float(info.get("mse_tracking", 0.0))
            ep_mse_sum += mse
            ep_steps += 1
            if terminated and bool(info.get("fallen")):
                episode_fell = True

        if ep_steps > 0:
            per_episode_mean_mse.append(ep_mse_sum / ep_steps)
            total_mse += ep_mse_sum
            total_steps += ep_steps
        if episode_fell:
            fall_episodes += 1

    mean_tracking_error_mse = float(total_mse / total_steps) if total_steps > 0 else 0.0
    return {
        "n_episodes": n_episodes,
        "total_env_steps": total_steps,
        "mean_tracking_error_mse": mean_tracking_error_mse,
        "mean_of_episode_mean_mse": float(np.mean(per_episode_mean_mse))
        if per_episode_mean_mse
        else 0.0,
        "fall_episodes": fall_episodes,
        "per_episode_mean_mse": per_episode_mean_mse,
    }


def apply_thresholds(metrics: dict[str, Any], thresholds: dict[str, Any]) -> tuple[bool, list[dict[str, str]]]:
    """Return (passed, failure_reasons) with human-readable messages."""
    reasons: list[dict[str, str]] = []
    mse = float(metrics["mean_tracking_error_mse"])
    falls = int(metrics["fall_episodes"])
    max_mse = float(thresholds["max_mean_mse"])
    max_falls = int(thresholds["max_fall_episodes"])

    if mse > max_mse:
        reasons.append(
            {
                "code": "tracking_mse_too_high",
                "message": (
                    f"Mean tracking MSE {mse:.6f} exceeds product threshold {max_mse:.6f} (rad²). "
                    "The policy may not track the reference closely enough."
                ),
            }
        )
    if falls > max_falls:
        reasons.append(
            {
                "code": "too_many_falls",
                "message": (
                    f"{falls} episode(s) ended in a fall; maximum allowed is {max_falls}. "
                    "Consider more training or adjusting the motion / rewards."
                ),
            }
        )
    return (len(reasons) == 0, reasons)


def build_validation_report(
    *,
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
    thresholds_path: str | None,
    reference_sha256: str | None,
    mjcf_sha256: str | None,
    checkpoint_path: str | None,
    val_seed: int,
    error: str | None = None,
) -> dict[str, Any]:
    if error:
        return {
            "validation_report_schema_ref": VALIDATION_REPORT_SCHEMA_REF,
            "applicable": True,
            "passed": False,
            "error": error,
            "failure_reasons": [
                {
                    "code": "validation_error",
                    "message": error,
                }
            ],
            "metrics": {},
            "thresholds_applied": thresholds,
            "thresholds_path": thresholds_path,
            "reference_sha256": reference_sha256,
            "mjcf_sha256": mjcf_sha256,
            "checkpoint_path": checkpoint_path,
            "val_seed": val_seed,
        }

    passed, failure_reasons = apply_thresholds(metrics, thresholds)
    return {
        "validation_report_schema_ref": VALIDATION_REPORT_SCHEMA_REF,
        "applicable": True,
        "passed": passed,
        "failure_reasons": failure_reasons,
        "metrics": {
            "mean_tracking_error_mse": metrics["mean_tracking_error_mse"],
            "mean_of_episode_mean_mse": metrics.get("mean_of_episode_mean_mse"),
            "fall_episodes": metrics["fall_episodes"],
            "n_episodes": metrics["n_episodes"],
            "total_env_steps": metrics.get("total_env_steps"),
        },
        "thresholds_applied": {
            "profile": thresholds.get("profile", "default"),
            "schema_version": thresholds.get("schema_version", "1.0.0"),
            "n_episodes": thresholds["n_episodes"],
            "max_mean_mse": thresholds["max_mean_mse"],
            "max_fall_episodes": thresholds["max_fall_episodes"],
        },
        "thresholds_path": thresholds_path,
        "reference_sha256": reference_sha256,
        "mjcf_sha256": mjcf_sha256,
        "checkpoint_path": checkpoint_path,
        "val_seed": val_seed,
    }


def run_product_validation(
    *,
    checkpoint_path: Path,
    reference_path: Path,
    train_config: dict[str, Any],
    thresholds: dict[str, Any],
    thresholds_path_label: str | None,
    val_seed: int,
) -> dict[str, Any]:
    """Load PPO zip, run N-episode eval, return validation report dict."""
    from stable_baselines3 import PPO

    ref_raw = load_reference_trajectory_json(reference_path)
    err = validate_reference_trajectory_dict(ref_raw)
    if err:
        raise ValueError("Invalid reference_trajectory.json:\n" + "\n".join(err))

    env_cfg = g1_env_cfg_from_train_config(train_config)
    env = G1TrackingEnv(ref_raw, env_cfg)
    model = PPO.load(str(checkpoint_path.expanduser().resolve()))

    th = normalize_thresholds(thresholds)
    n_ep = th["n_episodes"]
    metrics = evaluate_policy_tracking_metrics(
        model,
        env,
        n_episodes=n_ep,
        base_seed=val_seed,
        deterministic=True,
    )

    ref_sha = _sha256_file(reference_path.expanduser().resolve())
    mjcf_p = Path(str(env_cfg.mjcf_path)).expanduser().resolve()
    mjcf_sha = _sha256_file(mjcf_p) if mjcf_p.is_file() else None

    return build_validation_report(
        metrics=metrics,
        thresholds=th,
        thresholds_path=thresholds_path_label,
        reference_sha256=ref_sha,
        mjcf_sha256=mjcf_sha,
        checkpoint_path=str(checkpoint_path.expanduser().resolve()),
        val_seed=val_seed,
    )


def run_product_validation_safe(
    *,
    checkpoint_path: Path,
    reference_path: Path,
    train_config: dict[str, Any],
    thresholds_path: Path | None,
    val_seed: int,
    threshold_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Like :func:`run_product_validation` but never raises; errors become ``passed: false`` reports."""
    tpath = thresholds_path or default_thresholds_path()
    tlabel = str(tpath)
    try:
        th_raw = load_thresholds_file(tpath)
        if threshold_overrides:
            th_raw = {**th_raw, **threshold_overrides}
        th = normalize_thresholds(th_raw)
    except Exception as e:
        return build_validation_report(
            metrics={},
            thresholds={},
            thresholds_path=tlabel,
            reference_sha256=None,
            mjcf_sha256=None,
            checkpoint_path=str(checkpoint_path),
            val_seed=val_seed,
            error=f"invalid thresholds file: {e}",
        )

    try:
        return run_product_validation(
            checkpoint_path=checkpoint_path,
            reference_path=reference_path,
            train_config=train_config,
            thresholds=th,
            thresholds_path_label=tlabel,
            val_seed=val_seed,
        )
    except Exception as e:
        return build_validation_report(
            metrics={},
            thresholds=normalize_thresholds(th_raw),
            thresholds_path=tlabel,
            reference_sha256=None,
            mjcf_sha256=None,
            checkpoint_path=str(checkpoint_path),
            val_seed=val_seed,
            error=str(e),
        )


def write_validation_report_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def maybe_run_validation_after_train(
    *,
    output_dir: Path,
    checkpoint_path: Path,
    reference_path: Path,
    train_config: dict[str, Any],
    seed: int,
) -> dict[str, Any] | None:
    """
    If ``product_validation.enabled`` is not false, write ``validation_report.json`` under output_dir.

    Returns the report dict, or None if validation was skipped.
    """
    pv = train_config.get("product_validation") or {}
    if pv.get("enabled") is False:
        return None

    early = train_config.get("early_stop") or {}
    val_seed = int(pv.get("val_seed") if pv.get("val_seed") is not None else early.get("val_seed", seed + 1))

    th_path: Path | None = None
    raw_tp = pv.get("thresholds_path")
    if isinstance(raw_tp, str) and raw_tp.strip():
        th_path = Path(raw_tp).expanduser()

    overrides: dict[str, Any] | None = None
    if pv.get("n_episodes") is not None:
        overrides = {"n_episodes": int(pv["n_episodes"])}

    report = run_product_validation_safe(
        checkpoint_path=checkpoint_path,
        reference_path=reference_path,
        train_config=train_config,
        thresholds_path=th_path,
        val_seed=val_seed,
        threshold_overrides=overrides,
    )
    write_validation_report_json(output_dir / "validation_report.json", report)
    return report
