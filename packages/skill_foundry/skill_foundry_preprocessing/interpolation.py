"""
Keyframes → равномерная траектория (кубические сплайны по суставам).

Единицы: вход keyframes.json — градусы и секунды (фаза 0); выход — радианы.

Поведение по числу опорных кадров K на сустав:
- K == 1: позиция постоянна на всём [0, t_end]; скорость 0.
- K == 2: линейная интерполяция по времени (кубический сплайн из двух точек не используется).
- K >= 3: scipy.interpolate.CubicSpline с bc_type="natural".

Пропуски суставов в отдельных кадрах: forward-fill — переносится последнее известное
значение (в градусах) по времени; до первого явного значения для сустава используется 0°.

joint_velocities (MVP): первая производная соответствующего интерполянта в точках сетки
**до** клиппинга позиций; так скорость согласована с гладкой кривой в joint space.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
from scipy.interpolate import CubicSpline

from core_control.config.joint_limits import clamp_q

CANONICAL_JOINT_ORDER: list[str] = [str(i) for i in range(29)]


def _deg_to_rad(deg: float) -> float:
    return deg * (math.pi / 180.0)


def _strictly_increasing_times(frames: list[dict[str, Any]]) -> None:
    prev = -1.0
    for i, fr in enumerate(frames):
        ts = fr.get("timestamp_s")
        if not isinstance(ts, (int, float)):
            raise ValueError(f"keyframes[{i}]: timestamp_s must be numeric")
        ts = float(ts)
        if ts <= prev:
            raise ValueError(
                f"keyframes[{i}]: timestamp_s must be strictly increasing (got {ts} after {prev})"
            )
        prev = ts


def _collect_joint_union(frames: list[dict[str, Any]]) -> set[str]:
    u: set[str] = set()
    for fr in frames:
        jd = fr.get("joints_deg")
        if isinstance(jd, dict):
            u.update(jd.keys())
    return u


def _forward_fill_series(
    frames: list[dict[str, Any]], joint_ids: set[str]
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Для каждого joint_id — массивы времени (сек) и угла (рад) длины K."""
    prev_deg: dict[str, float] = {j: 0.0 for j in joint_ids}
    times_list: list[float] = []
    series: dict[str, list[float]] = {j: [] for j in joint_ids}

    for fr in frames:
        ts = float(fr["timestamp_s"])
        jd = fr.get("joints_deg")
        if not isinstance(jd, dict):
            raise ValueError("each keyframe must have joints_deg object")
        times_list.append(ts)
        for j in joint_ids:
            if j in jd:
                prev_deg[j] = float(jd[j])
            series[j].append(_deg_to_rad(prev_deg[j]))

    times = np.asarray(times_list, dtype=np.float64)
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for j in joint_ids:
        out[j] = (times, np.asarray(series[j], dtype=np.float64))
    return out


def _make_position_fn(times: np.ndarray, q: np.ndarray) -> tuple[Callable[[np.ndarray], np.ndarray], Callable[[np.ndarray], np.ndarray]]:
    """Возвращает (q(t), qdot(t)) для вектора времени t."""
    k = len(times)
    if k == 0:
        raise ValueError("empty time series")
    if k == 1:

        def q_fn(t: np.ndarray) -> np.ndarray:
            return np.full_like(t, float(q[0]), dtype=np.float64)

        def qd_fn(t: np.ndarray) -> np.ndarray:
            return np.zeros_like(t, dtype=np.float64)

        return q_fn, qd_fn
    if k == 2:
        t0, t1 = float(times[0]), float(times[1])
        q0, q1 = float(q[0]), float(q[1])
        slope = (q1 - q0) / (t1 - t0) if t1 != t0 else 0.0

        def q_fn(t: np.ndarray) -> np.ndarray:
            return q0 + slope * (t - t0)

        def qd_fn(t: np.ndarray) -> np.ndarray:
            return np.full_like(t, slope, dtype=np.float64)

        return q_fn, qd_fn

    sp = CubicSpline(times, q, bc_type="natural")
    der = sp.derivative()

    def q_fn(t: np.ndarray) -> np.ndarray:
        return np.asarray(sp(t), dtype=np.float64)

    def qd_fn(t: np.ndarray) -> np.ndarray:
        return np.asarray(der(t), dtype=np.float64)

    return q_fn, qd_fn


def _time_grid(t_end: float, frequency_hz: float) -> np.ndarray:
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")
    n = int(np.floor(t_end * frequency_hz))
    return np.arange(0, n + 1, dtype=np.float64) / frequency_hz


def keyframes_to_reference_trajectory(
    keyframes: dict[str, Any],
    frequency_hz: float,
    joint_order: list[str] | None = None,
    *,
    include_joint_velocities: bool = True,
) -> dict[str, Any]:
    """
    Строит словарь полей ReferenceTrajectory v1 из payload keyframes.json.

    :param keyframes: распарсенный JSON (schema 1.0.0), поле keyframes — список кадров.
    :param frequency_hz: целевая частота равномерной дискретизации.
    :param joint_order: порядок столбцов; по умолчанию "0".."28".
    :param include_joint_velocities: если True — добавить joint_velocities (производные сплайна до клиппинга q).
    """
    frames = keyframes.get("keyframes")
    if not isinstance(frames, list) or len(frames) == 0:
        raise ValueError("keyframes: keyframes must be a non-empty list")

    _strictly_increasing_times(frames)

    joint_union = _collect_joint_union(frames)
    if not joint_union:
        raise ValueError("keyframes: at least one joint must appear in some keyframe")

    series = _forward_fill_series(frames, joint_union)

    t_end = float(frames[-1]["timestamp_s"])
    t_grid = _time_grid(t_end, frequency_hz)

    order = joint_order if joint_order is not None else CANONICAL_JOINT_ORDER.copy()
    d = len(order)

    fns: dict[int, tuple[Callable[[np.ndarray], np.ndarray], Callable[[np.ndarray], np.ndarray]]] = {}
    for jid_str, (times, q_rad) in series.items():
        fns[int(jid_str)] = _make_position_fn(times, q_rad)

    joint_positions: list[list[float]] = []
    joint_velocities: list[list[float]] | None = [] if include_joint_velocities else None

    for ti in t_grid:
        row_q: list[float] = []
        row_qd: list[float] = []
        for idx in range(d):
            jid = int(order[idx])
            if jid in fns:
                q_fn, qd_fn = fns[jid]
                tvec = np.asarray([ti], dtype=np.float64)
                q_raw = float(q_fn(tvec)[0])
                qd_raw = float(qd_fn(tvec)[0])
            else:
                q_raw = 0.0
                qd_raw = 0.0
            row_q.append(clamp_q(jid, q_raw))
            row_qd.append(qd_raw)
        joint_positions.append(row_q)
        if joint_velocities is not None:
            joint_velocities.append(row_qd)

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "units": {"angle": "radians", "time": "seconds"},
        "frequency_hz": float(frequency_hz),
        "root_model": "root_not_in_reference",
        "joint_order": order,
        "joint_positions": joint_positions,
    }
    if joint_velocities is not None:
        payload["joint_velocities"] = joint_velocities
    return payload
