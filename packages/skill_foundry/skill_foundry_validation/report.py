"""Structured motion validation report (JSON-serializable)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    frame_index: int | None = None
    motor_index: int | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.frame_index is not None:
            d["frame_index"] = self.frame_index
        if self.motor_index is not None:
            d["motor_index"] = self.motor_index
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass
class MotionValidationReport:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    pinocchio_used: bool = False
    collision_engine: str = "not_run"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [i.to_dict() for i in self.issues],
            "pinocchio_used": self.pinocchio_used,
            "collision_engine": self.collision_engine,
            "notes": list(self.notes),
        }

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]
