import type { JointAngles } from "./telemetryTypes";
import { SKILL_KEYS_IN_JOINT_MAP_ORDER } from "../mujoco/jointMapping";

/** Cosine ease in [0,1] → [0,1], same as atomic_move.safe_move: (1 - cos(π t)) / 2 */
export function easeCosine01(u: number): number {
  const t = Math.min(1, Math.max(0, u));
  return (1.0 - Math.cos(t * Math.PI)) / 2.0;
}

const JOINT_COUNT = 29;

/** Read rad for joint index from map (telemetry uses "0".."28", WASM uses skill keys). */
export function jointRadAtIndex(joints: JointAngles, index: number): number {
  const idx = String(index);
  const sk = SKILL_KEYS_IN_JOINT_MAP_ORDER[index];
  const a = joints[idx];
  if (typeof a === "number" && Number.isFinite(a)) return a;
  const b = joints[sk];
  if (typeof b === "number" && Number.isFinite(b)) return b;
  return 0;
}

/** Linear interpolation between two poses (rad), all 29 joints. */
export function lerpJointAnglesRad(a: JointAngles, b: JointAngles, t: number): JointAngles {
  const out: JointAngles = {};
  const u = Math.min(1, Math.max(0, t));
  for (let i = 0; i < JOINT_COUNT; i++) {
    const sk = SKILL_KEYS_IN_JOINT_MAP_ORDER[i];
    const ra = jointRadAtIndex(a, i);
    const rb = jointRadAtIndex(b, i);
    out[sk] = ra + (rb - ra) * u;
  }
  return out;
}

/** Cosine-eased interpolation between two poses (rad). */
export function smoothStepJointAnglesRad(a: JointAngles, b: JointAngles, u01: number): JointAngles {
  return lerpJointAnglesRad(a, b, easeCosine01(u01));
}

/** Full 29-DOF map using skill keys (for WASM state and motion). */
export function captureFullJointAnglesSkillKeys(merged: JointAngles): JointAngles {
  const out: JointAngles = {};
  for (let i = 0; i < JOINT_COUNT; i++) {
    const sk = SKILL_KEYS_IN_JOINT_MAP_ORDER[i];
    const idx = String(i);
    const v =
      typeof merged[sk] === "number" && Number.isFinite(merged[sk])
        ? merged[sk]!
        : typeof merged[idx] === "number" && Number.isFinite(merged[idx])
          ? merged[idx]!
          : 0;
    out[sk] = v;
  }
  return out;
}

/** Max absolute angular delta (rad) across 29 joints. */
export function maxAbsDeltaRad(a: JointAngles, b: JointAngles): number {
  let m = 0;
  for (let i = 0; i < JOINT_COUNT; i++) {
    const d = Math.abs(jointRadAtIndex(b, i) - jointRadAtIndex(a, i));
    if (d > m) m = d;
  }
  return m;
}

/** Segment duration from max joint travel and nominal speed (rad/s), with a floor (seconds). */
export function segmentDurationSec(
  a: JointAngles,
  b: JointAngles,
  nominalSpeedRadS: number,
  minSec: number
): number {
  const dist = maxAbsDeltaRad(a, b);
  const speed = nominalSpeedRadS > 1e-6 ? nominalSpeedRadS : 0.5;
  const d = dist / speed;
  return Math.max(minSec, d);
}
