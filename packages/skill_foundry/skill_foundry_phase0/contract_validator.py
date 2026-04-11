import json
from pathlib import Path
from typing import Any


def _load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        errors.append(f"missing required file: {path.name}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name}: invalid json ({exc})")
        return None


def _ensure(condition: bool, msg: str, errors: list[str]) -> None:
    if not condition:
        errors.append(msg)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_keyframes(payload: dict[str, Any], errors: list[str]) -> None:
    _ensure(payload.get("schema_version") == "1.0.0", "keyframes: schema_version must be 1.0.0", errors)
    units = payload.get("units", {})
    _ensure(units.get("angle") == "degrees", "keyframes: units.angle must be degrees", errors)
    _ensure(units.get("time") == "seconds", "keyframes: units.time must be seconds", errors)
    frames = payload.get("keyframes")
    _ensure(isinstance(frames, list) and len(frames) > 0, "keyframes: keyframes must be non-empty list", errors)
    if not isinstance(frames, list):
        return
    prev_ts = -1.0
    for idx, frame in enumerate(frames):
        if not isinstance(frame, dict):
            errors.append(f"keyframes[{idx}]: must be object")
            continue
        ts = frame.get("timestamp_s")
        joints = frame.get("joints_deg")
        _ensure(_is_number(ts), f"keyframes[{idx}]: timestamp_s must be number", errors)
        _ensure(isinstance(joints, dict) and len(joints) > 0, f"keyframes[{idx}]: joints_deg must be non-empty object", errors)
        if _is_number(ts):
            _ensure(float(ts) >= 0.0, f"keyframes[{idx}]: timestamp_s must be >= 0", errors)
            _ensure(float(ts) > prev_ts, f"keyframes[{idx}]: timestamp_s must be strictly increasing", errors)
            prev_ts = float(ts)
        if isinstance(joints, dict):
            for joint_id, angle in joints.items():
                _ensure(str(joint_id).isdigit(), f"keyframes[{idx}]: joint id must be numeric string", errors)
                _ensure(_is_number(angle), f"keyframes[{idx}]: joint angle must be numeric", errors)


def _validate_motion(payload: dict[str, Any], errors: list[str]) -> None:
    _ensure(payload.get("schema_version") == "1.0.0", "motion: schema_version must be 1.0.0", errors)
    _ensure(isinstance(payload.get("motion_id"), str) and payload["motion_id"], "motion: motion_id must be non-empty string", errors)
    _ensure(
        isinstance(payload.get("source_keyframes_id"), str) and payload["source_keyframes_id"],
        "motion: source_keyframes_id must be non-empty string",
        errors,
    )
    stamps = payload.get("keyframe_timestamps_s")
    _ensure(isinstance(stamps, list) and len(stamps) > 0, "motion: keyframe_timestamps_s must be non-empty list", errors)
    if isinstance(stamps, list):
        prev_ts = -1.0
        for idx, ts in enumerate(stamps):
            _ensure(_is_number(ts), f"motion: keyframe_timestamps_s[{idx}] must be number", errors)
            if _is_number(ts):
                _ensure(float(ts) > prev_ts, f"motion: keyframe_timestamps_s[{idx}] must be strictly increasing", errors)
                prev_ts = float(ts)


def _validate_scenario(payload: dict[str, Any], errors: list[str]) -> None:
    _ensure(payload.get("schema_version") == "1.0.0", "scenario: schema_version must be 1.0.0", errors)
    _ensure(isinstance(payload.get("scenario_id"), str) and payload["scenario_id"], "scenario: scenario_id must be non-empty string", errors)
    steps = payload.get("steps")
    _ensure(isinstance(steps, list) and len(steps) > 0, "scenario: steps must be non-empty list", errors)
    if not isinstance(steps, list):
        return
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"scenario: steps[{idx}] must be object")
            continue
        _ensure(
            isinstance(step.get("motion_id"), str) and step["motion_id"],
            f"scenario: steps[{idx}].motion_id must be non-empty string",
            errors,
        )
        transition = step.get("transition")
        _ensure(isinstance(transition, dict), f"scenario: steps[{idx}].transition must be object", errors)
        if isinstance(transition, dict):
            t_type = transition.get("type")
            _ensure(t_type in {"on_complete", "after_seconds"}, f"scenario: steps[{idx}] transition.type invalid", errors)
            if t_type == "after_seconds":
                _ensure(_is_number(transition.get("seconds")), f"scenario: steps[{idx}] transition.seconds must be numeric", errors)


def _validate_reference(payload: dict[str, Any], errors: list[str]) -> None:
    _ensure(payload.get("schema_version") == "1.0.0", "reference: schema_version must be 1.0.0", errors)
    units = payload.get("units", {})
    _ensure(units.get("angle") == "radians", "reference: units.angle must be radians", errors)
    _ensure(units.get("time") == "seconds", "reference: units.time must be seconds", errors)
    _ensure(_is_number(payload.get("frequency_hz")) and payload["frequency_hz"] > 0, "reference: frequency_hz must be > 0", errors)
    _ensure(payload.get("root_model") == "root_not_in_reference", "reference: root_model must be root_not_in_reference", errors)

    joint_order = payload.get("joint_order")
    positions = payload.get("joint_positions")
    _ensure(isinstance(joint_order, list) and len(joint_order) > 0, "reference: joint_order must be non-empty list", errors)
    _ensure(isinstance(positions, list) and len(positions) > 0, "reference: joint_positions must be non-empty list", errors)
    if not (isinstance(joint_order, list) and isinstance(positions, list) and len(joint_order) > 0 and len(positions) > 0):
        return

    d = len(joint_order)
    for j in joint_order:
        _ensure(str(j).isdigit(), "reference: joint_order must contain numeric-string ids", errors)
    for t, row in enumerate(positions):
        _ensure(isinstance(row, list), f"reference: joint_positions[{t}] must be list", errors)
        if isinstance(row, list):
            _ensure(len(row) == d, f"reference: joint_positions[{t}] len must match joint_order", errors)
            for q in row:
                _ensure(_is_number(q), f"reference: joint_positions[{t}] must contain numeric values", errors)

    velocities = payload.get("joint_velocities")
    if velocities is not None:
        _ensure(isinstance(velocities, list) and len(velocities) == len(positions), "reference: joint_velocities must match T dimension", errors)
        if isinstance(velocities, list) and len(velocities) == len(positions):
            for t, row in enumerate(velocities):
                _ensure(isinstance(row, list) and len(row) == d, f"reference: joint_velocities[{t}] shape mismatch", errors)


def _validate_demo(payload: dict[str, Any], errors: list[str]) -> None:
    _ensure(payload.get("schema_version") == "1.0.0", "demo: schema_version must be 1.0.0", errors)
    _ensure(
        isinstance(payload.get("robot_model"), str) and payload["robot_model"],
        "demo: robot_model must be non-empty string",
        errors,
    )
    _ensure(_is_number(payload.get("sampling_hz")) and payload["sampling_hz"] > 0, "demo: sampling_hz must be > 0", errors)
    _ensure(isinstance(payload.get("obs_schema_ref"), str) and payload["obs_schema_ref"], "demo: obs_schema_ref must be non-empty string", errors)
    episodes = payload.get("episodes")
    _ensure(isinstance(episodes, list) and len(episodes) > 0, "demo: episodes must be non-empty list", errors)
    if not isinstance(episodes, list):
        return
    for e_idx, ep in enumerate(episodes):
        _ensure(isinstance(ep, dict), f"demo: episodes[{e_idx}] must be object", errors)
        if not isinstance(ep, dict):
            continue
        steps = ep.get("steps")
        _ensure(isinstance(steps, list) and len(steps) > 0, f"demo: episodes[{e_idx}].steps must be non-empty list", errors)
        if not isinstance(steps, list):
            continue
        done_count = 0
        for s_idx, step in enumerate(steps):
            _ensure(isinstance(step, dict), f"demo: step[{e_idx}:{s_idx}] must be object", errors)
            if not isinstance(step, dict):
                continue
            obs = step.get("obs")
            act = step.get("act")
            _ensure(isinstance(obs, list) and len(obs) > 0, f"demo: step[{e_idx}:{s_idx}] obs must be non-empty list", errors)
            _ensure(isinstance(act, list) and len(act) > 0, f"demo: step[{e_idx}:{s_idx}] act must be non-empty list", errors)
            _ensure(isinstance(step.get("done"), bool), f"demo: step[{e_idx}:{s_idx}] done must be bool", errors)
            if step.get("done") is True:
                done_count += 1
        _ensure(done_count == 1 and bool(steps[-1].get("done")), f"demo: episode[{e_idx}] must terminate exactly once on last step", errors)


def validate_keyframes_dict(payload: dict[str, Any]) -> list[str]:
    """Validate a keyframes.json payload (Phase 0 authoring)."""
    errors: list[str] = []
    _validate_keyframes(payload, errors)
    return errors


def validate_motion_dict(payload: dict[str, Any]) -> list[str]:
    """Validate a motion.json payload (Phase 0 authoring)."""
    errors: list[str] = []
    _validate_motion(payload, errors)
    return errors


def validate_scenario_dict(payload: dict[str, Any]) -> list[str]:
    """Validate a scenario.json payload (Phase 0 authoring)."""
    errors: list[str] = []
    _validate_scenario(payload, errors)
    return errors


def validate_reference_trajectory_dict(payload: dict[str, Any]) -> list[str]:
    """Validate a ReferenceTrajectory v1 dict (same rules as phase-0 directory validation)."""
    errors: list[str] = []
    _validate_reference(payload, errors)
    return errors


def validate_demonstration_dataset_dict(payload: dict[str, Any]) -> list[str]:
    """Validate a DemonstrationDataset v1 dict (same rules as phase-0 directory validation)."""
    errors: list[str] = []
    _validate_demo(payload, errors)
    return errors


def validate_phase0_directory(root_dir: Path | str) -> dict[str, Any]:
    root = Path(root_dir)
    errors: list[str] = []
    keyframes = _load_json(root / "keyframes.json", errors)
    motion = _load_json(root / "motion.json", errors)
    scenario = _load_json(root / "scenario.json", errors)
    reference = _load_json(root / "reference_trajectory.json", errors)
    demo = _load_json(root / "demonstration_dataset.json", errors)

    if keyframes is not None:
        _validate_keyframes(keyframes, errors)
    if motion is not None:
        _validate_motion(motion, errors)
    if scenario is not None:
        _validate_scenario(scenario, errors)
    if reference is not None:
        _validate_reference(reference, errors)
    if demo is not None:
        _validate_demo(demo, errors)

    return {"status": "ok" if not errors else "error", "errors": errors}

