"""
G1 Balance Environment for RL training.

Uses the browser G1 model with position actuators (ctrl = target angle).
The robot must stay standing while receiving random perturbations.

Action: 12-dim residual on leg joint TARGETS added to zero (standing).
Observation: pelvis orientation, angular velocity, leg joints, height, perturbation info.
Reward: stay upright + minimize energy.
"""

from __future__ import annotations
from typing import Any

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces


class G1BalanceEnv(gym.Env):
    """
    Balance task: stand in place under random perturbations.
    Uses position actuators (ctrl = desired joint angle).

    Episode = 10 seconds. Random pushes every 0.5-2s.
    Observation (43 dims):
      pelvis_quat (4) + pelvis_angvel (3) + pelvis_linvel (3) +
      leg_q (12) + leg_dq (12) + pelvis_z (1) +
      waist_targets (3) + arm_context (5)
    Action (12 dims):
      residual on 12 leg actuators (ctrl[0:12])
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        mjcf_path: str,
        sim_dt: float = 0.002,
        control_dt: float = 0.02,
        delta_max: float = 0.3,
        min_base_height: float = 0.35,
        max_episode_time: float = 10.0,
        push_force_range: tuple[float, float] = (30.0, 100.0),
        push_interval_range: tuple[float, float] = (0.5, 2.0),
        push_duration: float = 0.1,
        waist_perturbation_range: float = 0.3,
    ):
        super().__init__()
        self._mjcf_path = mjcf_path
        self._sim_dt = sim_dt
        self._control_dt = control_dt
        self._steps_per_control = max(1, int(round(control_dt / sim_dt)))
        self._delta_max = delta_max
        self._min_base_height = min_base_height
        self._max_episode_time = max_episode_time
        self._push_force_range = push_force_range
        self._push_interval_range = push_interval_range
        self._push_duration = push_duration
        self._waist_pert_range = waist_perturbation_range

        self._model = mujoco.MjModel.from_xml_path(mjcf_path)
        self._model.opt.timestep = sim_dt
        self._data = mujoco.MjData(self._model)

        self.nu = int(self._model.nu)
        assert self.nu == 29, f"Expected 29 actuators, got {self.nu}"

        # Find pelvis body id
        self._pelvis_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_BODY, "pelvis")

        # Observation: 43 dims
        obs_dim = 4 + 3 + 3 + 12 + 12 + 1 + 3 + 5  # = 43
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float64
        )

        # Action: 12 leg joint target residuals
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(12,), dtype=np.float64
        )

        # State
        self._time = 0.0
        self._prev_action = np.zeros(12)
        self._next_push_time = 0.0
        self._push_end_time = 0.0
        self._push_force = np.zeros(3)
        self._waist_targets = np.zeros(3)

    def _schedule_next_push(self):
        interval = self.np_random.uniform(*self._push_interval_range)
        self._next_push_time = self._time + interval

        angle = self.np_random.uniform(0, 2 * np.pi)
        magnitude = self.np_random.uniform(*self._push_force_range)
        self._push_force = np.array([
            magnitude * np.cos(angle),
            magnitude * np.sin(angle),
            self.np_random.uniform(-10, 10),
        ])
        self._push_end_time = self._next_push_time + self._push_duration

    def _randomize_waist(self):
        self._waist_targets = self.np_random.uniform(
            -self._waist_pert_range,
            self._waist_pert_range,
            size=3,
        )

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)

        mujoco.mj_resetData(self._model, self._data)
        self._time = 0.0
        self._prev_action = np.zeros(12)

        self._data.ctrl[:] = 0.0

        self._next_push_time = self.np_random.uniform(0.5, 1.5)
        self._push_end_time = 0.0
        self._push_force = np.zeros(3)
        self._waist_targets = np.zeros(3)

        for _ in range(50):
            mujoco.mj_step(self._model, self._data)
        self._time = 0.0

        mujoco.mj_forward(self._model, self._data)
        return self._get_obs(), {}

    def _get_obs(self) -> np.ndarray:
        pelvis_quat = self._data.qpos[3:7].copy()
        pelvis_angvel = self._data.qvel[3:6].copy()
        pelvis_linvel = self._data.qvel[0:3].copy()
        pelvis_z = np.array([self._data.qpos[2]])

        leg_q = self._data.qpos[7:19].copy()
        leg_dq = self._data.qvel[6:18].copy()

        waist = self._waist_targets.copy()

        arm_context = np.array([
            self._data.ctrl[15],
            self._data.ctrl[22],
            self._data.ctrl[18],
            self._data.ctrl[25],
            self._data.ctrl[14],
        ])

        return np.concatenate([
            pelvis_quat,     # 4
            pelvis_angvel,   # 3
            pelvis_linvel,   # 3
            leg_q,           # 12
            leg_dq,          # 12
            pelvis_z,        # 1
            waist,           # 3
            arm_context,     # 5
        ]).astype(np.float64)

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        action = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        delta = action * self._delta_max

        self._data.ctrl[:] = 0.0

        self._data.ctrl[12] = self._waist_targets[0]
        self._data.ctrl[13] = self._waist_targets[1]
        self._data.ctrl[14] = self._waist_targets[2]

        for i in range(12):
            self._data.ctrl[i] = delta[i]

        for _ in range(self._steps_per_control):
            self._data.xfrc_applied[self._pelvis_id, :] = 0
            if self._next_push_time <= self._time < self._push_end_time:
                self._data.xfrc_applied[self._pelvis_id, :3] = self._push_force

            mujoco.mj_step(self._model, self._data)
            self._time += self._sim_dt

            if self._time >= self._push_end_time and self._time >= self._next_push_time:
                self._schedule_next_push()
                if self.np_random.random() < 0.3:
                    self._randomize_waist()

        height = float(self._data.qpos[2])
        fallen = height < self._min_base_height

        qw = self._data.qpos[3]
        upright = 2.0 * (qw ** 2) - 1.0
        r_upright = max(0, upright)

        r_height = max(0, min(1, (height - self._min_base_height) / (0.79 - self._min_base_height)))

        r_alive = 0.5 if not fallen else 0.0

        energy = float(np.sum(delta ** 2))
        r_energy = -0.01 * energy

        jerk = float(np.sum((action - self._prev_action) ** 2))
        r_jerk = -0.005 * jerk
        self._prev_action = action.copy()

        reward = 2.0 * r_upright + 1.0 * r_height + r_alive + r_energy + r_jerk

        terminated = bool(fallen)
        truncated = self._time >= self._max_episode_time

        info = {
            "r_upright": r_upright,
            "r_height": r_height,
            "r_alive": r_alive,
            "r_energy": r_energy,
            "r_jerk": r_jerk,
            "base_height": height,
            "fallen": fallen,
            "time": self._time,
            "upright_cos": upright,
        }

        return self._get_obs(), reward, terminated, truncated, info
