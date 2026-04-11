import type { JointAngles } from "./telemetryTypes";
import { SKILL_KEYS_IN_JOINT_MAP_ORDER } from "../mujoco/jointMapping";

/**
 * React Router `location.state`: prefill keyframes JSON (Phase 0) from Motion Studio → Authoring / Pipeline.
 */
export const KEYFRAMES_PREFILL_STATE_KEY = "prefillKeyframesJson";

export function extractKeyframesPrefillFromLocationState(state: unknown): string | null {
  if (!state || typeof state !== "object") return null;
  const v = (state as Record<string, unknown>)[KEYFRAMES_PREFILL_STATE_KEY];
  return typeof v === "string" && v.trim() ? v : null;
}

const RAD2DEG = 180 / Math.PI;
const JOINT_INDEX_COUNT = 29;

/**
 * Phase 0 `joints_deg` with keys "0"…"28" (degrees). Resolves telemetry index keys and WASM skill keys.
 */
export function jointAnglesRadToJointsDegPhase0(joints: JointAngles): Record<string, number> {
  const out: Record<string, number> = {};
  for (let i = 0; i < JOINT_INDEX_COUNT; i++) {
    const idx = String(i);
    const sk = SKILL_KEYS_IN_JOINT_MAP_ORDER[i];
    const rad =
      typeof joints[idx] === "number" && Number.isFinite(joints[idx])
        ? joints[idx]!
        : typeof joints[sk] === "number" && Number.isFinite(joints[sk])
          ? joints[sk]!
          : 0;
    out[idx] = rad * RAD2DEG;
  }
  return out;
}

/** Alias for {@link jointAnglesRadToJointsDegPhase0}. */
export function jointRadMapToJointsDeg(joints: JointAngles): Record<string, number> {
  return jointAnglesRadToJointsDegPhase0(joints);
}

export type BuildKeyframesOptions = {
  schemaVersion?: string;
  robotModel?: string;
  timestampS?: number;
};

export type BuildKeyframesFromPosesOptions = BuildKeyframesOptions & {
  /** Seconds between consecutive keyframes (default 0.5). */
  timestampStepS?: number;
};

/**
 * Single-keyframe Phase 0 document from a telemetry snapshot (angles in rad → degrees in JSON).
 */
export function buildKeyframesDocumentFromJointRad(
  jointsRad: JointAngles,
  opts: BuildKeyframesOptions = {}
): Record<string, unknown> {
  const schema_version = opts.schemaVersion ?? "1.0.0";
  const robot_model = opts.robotModel ?? "g1_29dof";
  const timestamp_s = typeof opts.timestampS === "number" && Number.isFinite(opts.timestampS) ? opts.timestampS : 0;
  const joints_deg = jointAnglesRadToJointsDegPhase0(jointsRad);
  return {
    schema_version,
    robot_model,
    units: { angle: "degrees", time: "seconds" },
    keyframes: [{ timestamp_s, joints_deg }],
  };
}

/**
 * Phase 0 document with multiple keyframes (same poses drive Authoring / Pipeline / pose-drafts).
 */
export function buildKeyframesDocumentFromPoses(
  posesRad: JointAngles[],
  opts: BuildKeyframesFromPosesOptions = {}
): Record<string, unknown> {
  if (posesRad.length === 0) {
    throw new Error("posesRad must not be empty");
  }
  const schema_version = opts.schemaVersion ?? "1.0.0";
  const robot_model = opts.robotModel ?? "g1_29dof";
  const step =
    typeof opts.timestampStepS === "number" && Number.isFinite(opts.timestampStepS) && opts.timestampStepS > 0
      ? opts.timestampStepS
      : 0.5;
  const baseTs = typeof opts.timestampS === "number" && Number.isFinite(opts.timestampS) ? opts.timestampS : 0;

  const keyframes = posesRad.map((pose, i) => ({
    timestamp_s: baseTs + i * step,
    joints_deg: jointAnglesRadToJointsDegPhase0(pose),
  }));

  return {
    schema_version,
    robot_model,
    units: { angle: "degrees", time: "seconds" },
    keyframes,
  };
}

/**
 * SDK `pose.json` shape: top-level JSON array of per-joint degree maps (`action_exporter` / `_load_poses_deg`).
 */
export function buildSdkPoseJsonArray(posesRad: JointAngles[]): Record<string, number>[] {
  return posesRad.map((p) => jointAnglesRadToJointsDegPhase0(p));
}

export function stringifySdkPoseJson(posesDeg: Record<string, number>[]): string {
  return `${JSON.stringify(posesDeg, null, 2)}\n`;
}

export function stringifyKeyframesDocument(doc: Record<string, unknown>): string {
  return `${JSON.stringify(doc, null, 2)}\n`;
}
