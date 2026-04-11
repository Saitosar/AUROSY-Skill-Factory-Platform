"""Tests for kinematic validation (no Pinocchio required)."""

from __future__ import annotations

import unittest

from skill_foundry_validation.kinematic_validator import validate_kinematics


def _minimal_reference(joint_positions: list[list[float]]) -> dict:
    order = [str(i) for i in range(29)]
    return {
        "schema_version": "1.0.0",
        "units": {"angle": "radians", "time": "seconds"},
        "frequency_hz": 50.0,
        "root_model": "root_not_in_reference",
        "joint_order": order,
        "joint_positions": joint_positions,
    }


class TestKinematicValidator(unittest.TestCase):
    def test_ok_flat_trajectory(self) -> None:
        zero = [0.0] * 29
        ref = _minimal_reference([zero, zero])
        r = validate_kinematics(ref)
        self.assertTrue(r.ok)
        self.assertEqual(len(r.errors), 0)

    def test_position_violation(self) -> None:
        zero = [0.0] * 29
        bad = [0.0] * 29
        bad[0] = 10.0  # far outside hip pitch limits
        ref = _minimal_reference([zero, bad])
        r = validate_kinematics(ref)
        self.assertFalse(r.ok)
        self.assertTrue(any(i.code == "position_limit" for i in r.issues))


if __name__ == "__main__":
    unittest.main()
