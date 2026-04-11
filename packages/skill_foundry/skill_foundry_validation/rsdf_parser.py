"""
RSDF helpers (mc_rtc / Unitree).

The ``isri-aist/g1_description`` package ships small per-link RSDF XML files (e.g. foot
surfaces), not a global disabled-collision list. For Pinocchio collision pairs, prefer
building pairs from the URDF / geometry model or using MuJoCo contact checks in
:mod:`skill_foundry_validation.collision_mujoco`.
"""

from __future__ import annotations

# Reserved for future: parse mc_rtc global RSDF if upstream adds it.
