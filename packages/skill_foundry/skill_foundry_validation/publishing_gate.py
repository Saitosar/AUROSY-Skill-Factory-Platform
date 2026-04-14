"""Publishing gate criteria for motion skill bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PublishingCriteria:
    """Configuration for publishing gate checks."""

    tracking_max_mse: float = 0.1
    max_fall_rate: float = 0.05
    min_eval_episodes: int = 10
    min_discriminator_score: float = 0.3
    max_energy_per_step: float = 100.0
    max_foot_sliding: float = 0.05
    require_eval_motion: bool = True


@dataclass
class PublishingGateResult:
    """Result of publishing gate evaluation."""

    passed: bool
    criteria_met: dict[str, bool] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    failure_reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "criteria_met": self.criteria_met,
            "metrics": self.metrics,
            "failure_reasons": self.failure_reasons,
            "notes": self.notes,
        }


def evaluate_publishing_gate(
    eval_motion: dict[str, Any] | None,
    train_run: dict[str, Any] | None = None,
    criteria: PublishingCriteria | None = None,
) -> PublishingGateResult:
    """Evaluate whether a trained motion skill meets publishing criteria.

    Args:
        eval_motion: Contents of eval_motion.json from training run
        train_run: Optional contents of train_run.json with training metadata
        criteria: Publishing criteria configuration

    Returns:
        PublishingGateResult with pass/fail status and detailed breakdown
    """
    cfg = criteria or PublishingCriteria()
    criteria_met: dict[str, bool] = {}
    metrics: dict[str, Any] = {}
    failure_reasons: list[str] = []
    notes: list[str] = []

    if cfg.require_eval_motion and eval_motion is None:
        return PublishingGateResult(
            passed=False,
            criteria_met={"eval_motion_exists": False},
            failure_reasons=["eval_motion.json is required but not found"],
        )

    criteria_met["eval_motion_exists"] = eval_motion is not None

    if eval_motion is None:
        return PublishingGateResult(
            passed=True,
            criteria_met=criteria_met,
            notes=["eval_motion.json not provided, skipping quality checks"],
        )

    tracking_mse = eval_motion.get("tracking_mean_mse")
    if tracking_mse is not None:
        metrics["tracking_mean_mse"] = tracking_mse
        passed = tracking_mse <= cfg.tracking_max_mse
        criteria_met["tracking_mse"] = passed
        if not passed:
            failure_reasons.append(
                f"Tracking MSE {tracking_mse:.4f} exceeds maximum {cfg.tracking_max_mse}"
            )

    fall_rate = eval_motion.get("fall_rate")
    if fall_rate is None:
        product_val = eval_motion.get("product_validation", {})
        if isinstance(product_val, dict):
            fall_rate = product_val.get("fall_rate")

    if fall_rate is not None:
        metrics["fall_rate"] = fall_rate
        passed = fall_rate <= cfg.max_fall_rate
        criteria_met["fall_rate"] = passed
        if not passed:
            failure_reasons.append(
                f"Fall rate {fall_rate:.2%} exceeds maximum {cfg.max_fall_rate:.2%}"
            )

    eval_episodes = eval_motion.get("eval_episodes", eval_motion.get("n_episodes"))
    if eval_episodes is not None:
        metrics["eval_episodes"] = eval_episodes
        passed = eval_episodes >= cfg.min_eval_episodes
        criteria_met["eval_episodes"] = passed
        if not passed:
            failure_reasons.append(
                f"Eval episodes {eval_episodes} below minimum {cfg.min_eval_episodes}"
            )

    disc_score = eval_motion.get("discriminator_score", eval_motion.get("amp_score"))
    if disc_score is not None:
        metrics["discriminator_score"] = disc_score
        passed = disc_score >= cfg.min_discriminator_score
        criteria_met["discriminator_score"] = passed
        if not passed:
            failure_reasons.append(
                f"Discriminator score {disc_score:.3f} below minimum {cfg.min_discriminator_score}"
            )
        else:
            notes.append(f"Motion naturalness score: {disc_score:.3f}")

    energy = eval_motion.get("mean_energy_per_step")
    if energy is not None:
        metrics["mean_energy_per_step"] = energy
        passed = energy <= cfg.max_energy_per_step
        criteria_met["energy"] = passed
        if not passed:
            failure_reasons.append(
                f"Energy {energy:.1f} per step exceeds maximum {cfg.max_energy_per_step}"
            )

    foot_sliding = eval_motion.get("foot_sliding_proxy")
    if foot_sliding is not None:
        metrics["foot_sliding_proxy"] = foot_sliding
        passed = foot_sliding <= cfg.max_foot_sliding
        criteria_met["foot_sliding"] = passed
        if not passed:
            failure_reasons.append(
                f"Foot sliding {foot_sliding:.3f} exceeds maximum {cfg.max_foot_sliding}"
            )

    velocity_consistency = eval_motion.get("velocity_consistency")
    if velocity_consistency is not None:
        metrics["velocity_consistency"] = velocity_consistency
        notes.append(f"Velocity consistency: {velocity_consistency:.3f}")

    if train_run is not None:
        if "total_timesteps" in train_run:
            metrics["total_timesteps"] = train_run["total_timesteps"]
        if "final_reward" in train_run:
            metrics["final_reward"] = train_run["final_reward"]
        if "mode" in train_run:
            metrics["training_mode"] = train_run["mode"]

    all_passed = all(criteria_met.values()) and len(failure_reasons) == 0

    if all_passed:
        notes.append("All publishing criteria met - skill is ready for deployment")
    else:
        notes.append(f"Publishing blocked: {len(failure_reasons)} criterion/criteria not met")

    return PublishingGateResult(
        passed=all_passed,
        criteria_met=criteria_met,
        metrics=metrics,
        failure_reasons=failure_reasons,
        notes=notes,
    )


def evaluate_publishing_gate_from_paths(
    eval_motion_path: str | Path | None,
    train_run_path: str | Path | None = None,
    criteria: PublishingCriteria | None = None,
) -> PublishingGateResult:
    """Load eval_motion and train_run from files and evaluate publishing gate.

    Args:
        eval_motion_path: Path to eval_motion.json (can be None)
        train_run_path: Optional path to train_run.json
        criteria: Publishing criteria configuration

    Returns:
        PublishingGateResult with pass/fail status and detailed breakdown
    """
    eval_motion: dict[str, Any] | None = None
    train_run: dict[str, Any] | None = None

    if eval_motion_path is not None:
        p = Path(eval_motion_path)
        if p.is_file():
            try:
                eval_motion = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    if train_run_path is not None:
        p = Path(train_run_path)
        if p.is_file():
            try:
                train_run = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    return evaluate_publishing_gate(eval_motion, train_run, criteria)


def check_bundle_publishable(
    bundle_dir: Path | str,
    criteria: PublishingCriteria | None = None,
) -> PublishingGateResult:
    """Check if a skill bundle directory meets publishing criteria.

    Args:
        bundle_dir: Path to unpacked skill bundle directory
        criteria: Publishing criteria configuration

    Returns:
        PublishingGateResult with pass/fail status
    """
    bundle_path = Path(bundle_dir)

    eval_motion_path = bundle_path / "eval_motion.json"
    train_run_path = bundle_path / "train_run.json"

    return evaluate_publishing_gate_from_paths(
        eval_motion_path if eval_motion_path.exists() else None,
        train_run_path if train_run_path.exists() else None,
        criteria,
    )
