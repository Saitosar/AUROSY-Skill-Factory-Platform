from __future__ import annotations

import numpy as np

from skill_foundry_rl.reference_motion import reference_motion_from_dict


def _reference_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "robot_model": "g1_29dof",
        "units": {"angle": "radians", "time": "seconds"},
        "frequency_hz": 50.0,
        "root_model": "root_not_in_reference",
        "joint_order": [str(i) for i in range(29)],
        "joint_positions": [[0.01 * i for i in range(29)] for _ in range(6)],
    }


def test_reference_motion_duration_and_dt() -> None:
    rm = reference_motion_from_dict(_reference_payload())
    assert rm.dt == 0.02
    assert rm.num_samples == 6
    assert rm.duration_sec == 0.1


def test_reference_motion_samples_expert_transition_shapes() -> None:
    rm = reference_motion_from_dict(_reference_payload())
    rng = np.random.default_rng(7)
    s0, s1 = rm.sample_expert_states(rng, 8)
    assert s0.shape == (8, 87)
    assert s1.shape == (8, 87)
    # Expert rows are projected as perfect tracking states.
    assert np.allclose(s0[:, 58:], 0.0)
    assert np.allclose(s1[:, 58:], 0.0)
