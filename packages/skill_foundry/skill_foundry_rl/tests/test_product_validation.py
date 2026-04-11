"""Unit tests for product validation thresholds (no MuJoCo)."""

from __future__ import annotations

from skill_foundry_rl.product_validation import apply_thresholds


def test_apply_thresholds_pass() -> None:
    metrics = {"mean_tracking_error_mse": 0.01, "fall_episodes": 0}
    th = {"max_mean_mse": 0.15, "max_fall_episodes": 2, "n_episodes": 10}
    ok, reasons = apply_thresholds(metrics, th)
    assert ok is True
    assert reasons == []


def test_apply_thresholds_mse_fail() -> None:
    metrics = {"mean_tracking_error_mse": 0.5, "fall_episodes": 0}
    th = {"max_mean_mse": 0.15, "max_fall_episodes": 2, "n_episodes": 10}
    ok, reasons = apply_thresholds(metrics, th)
    assert ok is False
    assert any(r["code"] == "tracking_mse_too_high" for r in reasons)


def test_apply_thresholds_falls_fail() -> None:
    metrics = {"mean_tracking_error_mse": 0.01, "fall_episodes": 5}
    th = {"max_mean_mse": 0.15, "max_fall_episodes": 2, "n_episodes": 10}
    ok, reasons = apply_thresholds(metrics, th)
    assert ok is False
    assert any(r["code"] == "too_many_falls" for r in reasons)
