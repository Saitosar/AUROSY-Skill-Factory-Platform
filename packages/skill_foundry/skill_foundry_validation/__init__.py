"""Offline motion validation for G1 ReferenceTrajectory (kinematic, dynamic, self-collision)."""

from __future__ import annotations

from skill_foundry_validation.motion_validator import MotionValidatorConfig, validate_reference_motion
from skill_foundry_validation.report import MotionValidationReport
from skill_foundry_validation.pretraining_validator import (
    PreTrainingConfig,
    PreTrainingResult,
    validate_pretraining,
    validate_pretraining_from_path,
)
from skill_foundry_validation.publishing_gate import (
    PublishingCriteria,
    PublishingGateResult,
    evaluate_publishing_gate,
    evaluate_publishing_gate_from_paths,
    check_bundle_publishable,
)

__all__ = [
    "MotionValidationReport",
    "MotionValidatorConfig",
    "validate_reference_motion",
    "PreTrainingConfig",
    "PreTrainingResult",
    "validate_pretraining",
    "validate_pretraining_from_path",
    "PublishingCriteria",
    "PublishingGateResult",
    "evaluate_publishing_gate",
    "evaluate_publishing_gate_from_paths",
    "check_bundle_publishable",
]
