"""
Gymnasium MuJoCo environment: residual PD tracking of ReferenceTrajectory v1.

Action: per-motor delta added to reference joint targets (then same PD as skill_foundry_sim playback).
Observation: motor_q, motor_dq, (q_meas - q_ref); optional IMU sensors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

from skill_foundry_sim.trajectory_sampler import sample_trajectory_at_times

from skill_foundry_rl.obs_schema import IMU_SENSOR_NAMES, rl_obs_dim


@dataclass
class G1TrackingEnvConfig:
    """Environment hyperparameters (subset also mirrored in train YAML)."""

    mjcf_path: str
    sim_dt: float = 0.005
    kp: float = 150.0
    kd: float = 5.0
    delta_max: float = 0.25
    """Max residual on q_des per motor (radians), applied after scaling policy output from [-1, 1]."""
    min_base_height: float = 0.35
    """Terminate if pelvis height (free joint z) falls below this value (meters)."""
    max_episode_steps: int | None = None
    """If set, truncate after this many steps regardless of trajectory length."""
    include_imu_in_obs: bool = False
    reward_weights: dict[str, float] | None = None
    """Keys: w_track, w_alive, w_energy, w_jerk (defaults applied if missing)."""


def _default_reward_weights() -> dict[str, float]:
    return {
        "w_track": 1.0,
        "w_alive": 0.02,
        "w_energy": 1.0e-5,
        "w_jerk": 1.0e-6,
    }


def g1_env_cfg_from_train_config(config: dict[str, Any]) -> G1TrackingEnvConfig:
    """Build :class:`G1TrackingEnvConfig` from a train config dict (``env`` + optional top-level ``mjcf_path``)."""
    env_cfg_dict = config.get("env") or {}
    mjcf_path = env_cfg_dict.get("mjcf_path") or config.get("mjcf_path")
    if not mjcf_path:
        raise ValueError(
            "train config must set env.mjcf_path (path to G1 MJCF, e.g. scene_29dof.xml)"
        )
    return G1TrackingEnvConfig(
        mjcf_path=str(mjcf_path),
        sim_dt=float(env_cfg_dict.get("sim_dt", 0.005)),
        kp=float(env_cfg_dict.get("kp", 150.0)),
        kd=float(env_cfg_dict.get("kd", 5.0)),
        delta_max=float(env_cfg_dict.get("delta_max", 0.25)),
        min_base_height=float(env_cfg_dict.get("min_base_height", 0.35)),
        max_episode_steps=env_cfg_dict.get("max_episode_steps"),
        include_imu_in_obs=bool(env_cfg_dict.get("include_imu_in_obs", False)),
        reward_weights=env_cfg_dict.get("reward_weights"),
    )


class G1TrackingEnv(gym.Env):
    """
    Single ReferenceTrajectory episode: time starts at 0; each step advances by ``sim_dt``.

    Metadata:
        ``render_modes``: ``None`` (headless).
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        reference: dict[str, Any],
        config: G1TrackingEnvConfig,
    ) -> None:
        super().__init__()
        self._reference = reference
        self._cfg = config
        self._joint_positions = reference["joint_positions"]
        self._frequency_hz = float(reference["frequency_hz"])
        self._joint_order = reference["joint_order"]
        self._joint_velocities = reference.get("joint_velocities")
        t_samples = len(self._joint_positions)
        self._t_max = (t_samples - 1) / self._frequency_hz

        self._model = mujoco.MjModel.from_xml_path(config.mjcf_path)
        self._model.opt.timestep = config.sim_dt
        self._data = mujoco.MjData(self._model)
        self.nu = int(self._model.nu)
        if self.nu != 29:
            raise ValueError(f"expected 29 actuators for G1 29DoF profile, got nu={self.nu}")

        obs_dim = rl_obs_dim(include_imu=config.include_imu_in_obs)
        self.include_imu = config.include_imu_in_obs
        self._imu_adrs: list[tuple[int, int]] = []
        if config.include_imu_in_obs:
            for name in IMU_SENSOR_NAMES:
                sid = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_SENSOR, name)
                if sid < 0:
                    raise RuntimeError(f"sensor not found in MJCF: {name}")
                adr = int(self._model.sensor_adr[sid])
                dim = int(self._model.sensor_dim[sid])
                self._imu_adrs.append((adr, dim))

        high = np.inf * np.ones(obs_dim, dtype=np.float64)
        self.observation_space = spaces.Box(-high, high, dtype=np.float64)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(self.nu,), dtype=np.float64)

        self._reward_weights = {**_default_reward_weights(), **(config.reward_weights or {})}
        self._max_episode_steps = config.max_episode_steps
        self._prev_ctrl = np.zeros(self.nu, dtype=np.float64)
        self._step_idx = 0
        self._episode_time = 0.0

    @property
    def reference(self) -> dict[str, Any]:
        return self._reference

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)

        mujoco.mj_resetData(self._model, self._data)
        self._step_idx = 0
        self._episode_time = 0.0
        self._prev_ctrl = np.zeros(self.nu, dtype=np.float64)
        mujoco.mj_forward(self._model, self._data)
        obs = self._get_obs()
        return obs, {}

    def _ref_row_at(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        times = np.array([t], dtype=np.float64)
        q_cols, dq_cols = sample_trajectory_at_times(
            self._joint_positions,
            self._frequency_hz,
            times,
            joint_velocities=self._joint_velocities,
        )
        return q_cols[0], dq_cols[0]

    def _build_q_dq_des(
        self,
        row_q: np.ndarray,
        row_dq: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Motor-order desired q, dq (same construction as headless_playback dynamic)."""
        q_des = self._data.sensordata[: self.nu].copy()
        dq_des = self._data.sensordata[self.nu : 2 * self.nu].copy()
        for col, jid_str in enumerate(self._joint_order):
            mi = int(str(jid_str))
            q_des[mi] = row_q[col]
            dq_des[mi] = row_dq[col]
        return q_des, dq_des

    def _build_q_ref_motor(self, row_q: np.ndarray, motor_q: np.ndarray) -> np.ndarray:
        """Reference motor angles: unspecified motors track current measured (zero tracking error by design)."""
        q_ref = motor_q.copy()
        for col, jid_str in enumerate(self._joint_order):
            mi = int(str(jid_str))
            q_ref[mi] = row_q[col]
        return q_ref

    def _base_height(self) -> float:
        """Pelvis free joint world z (qpos[2])."""
        return float(self._data.qpos[2])

    def _get_obs(self) -> np.ndarray:
        q = self._data.sensordata[: self.nu].copy()
        dq = self._data.sensordata[self.nu : 2 * self.nu].copy()
        row_q, _row_dq = self._ref_row_at(self._episode_time)
        q_ref = self._build_q_ref_motor(row_q, q)
        err = q - q_ref
        parts = [q, dq, err]
        if self.include_imu:
            imu_blocks: list[np.ndarray] = []
            for adr, dim in self._imu_adrs:
                imu_blocks.append(self._data.sensordata[adr : adr + dim].copy())
            parts.append(np.concatenate(imu_blocks))
        return np.concatenate(parts).astype(np.float64)

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        action = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        delta = action * self._cfg.delta_max

        t_start = self._episode_time
        row_q, row_dq = self._ref_row_at(t_start)
        q_des, dq_des = self._build_q_dq_des(row_q, row_dq)
        q_des = q_des + delta

        for i in range(self.nu):
            q_m = self._data.sensordata[i]
            dq_m = self._data.sensordata[self.nu + i]
            self._data.ctrl[i] = self._cfg.kp * (q_des[i] - q_m) + self._cfg.kd * (dq_des[i] - dq_m)

        ctrl = self._data.ctrl.copy()
        mujoco.mj_step(self._model, self._data)
        t_next = t_start + self._cfg.sim_dt
        self._episode_time = t_next
        self._step_idx += 1

        row_q_next, _ = self._ref_row_at(t_next)
        q = self._data.sensordata[: self.nu].copy()
        q_ref = self._build_q_ref_motor(row_q_next, q)
        err = q - q_ref
        mse_track = float(np.mean(err**2))
        r_track = -self._reward_weights["w_track"] * mse_track

        height = self._base_height()
        fallen = height < self._cfg.min_base_height
        r_alive = self._reward_weights["w_alive"] if not fallen else 0.0

        energy = float(np.sum(ctrl**2))
        r_energy = -self._reward_weights["w_energy"] * energy

        jerk = float(np.sum((ctrl - self._prev_ctrl) ** 2))
        r_jerk = -self._reward_weights["w_jerk"] * jerk
        self._prev_ctrl = ctrl.copy()

        reward = r_track + r_alive + r_energy + r_jerk

        terminated = bool(fallen)
        past_reference = t_next > self._t_max + 1e-9
        steps_exceeded = self._max_episode_steps is not None and self._step_idx >= self._max_episode_steps
        truncated = bool(past_reference or steps_exceeded)

        info = {
            "r_track": r_track,
            "r_alive": r_alive,
            "r_energy": r_energy,
            "r_jerk": r_jerk,
            "mse_tracking": mse_track,
            "base_height": height,
            "fallen": fallen,
        }
        obs = self._get_obs()
        return obs, reward, terminated, truncated, info
