import { SKILL_KEYS_IN_JOINT_MAP_ORDER } from "../mujoco/jointMapping";

/** Same index grouping as desktop Pose Studio / typical backend `GET /api/joints`. */
export const WASM_FALLBACK_JOINT_INDICES = {
  leftArm: [15, 16, 17, 18, 19, 20, 21],
  rightArm: [22, 23, 24, 25, 26, 27, 28],
  torso: [12, 13, 14],
  legs: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
} as const;

/** `GET /api/joints`-shaped joint_map when the API is offline (indices → skill keys). */
export function defaultJointMapFromSkillKeys(): Record<string, string> {
  const m: Record<string, string> = {};
  SKILL_KEYS_IN_JOINT_MAP_ORDER.forEach((key, i) => {
    m[String(i)] = key;
  });
  return m;
}
