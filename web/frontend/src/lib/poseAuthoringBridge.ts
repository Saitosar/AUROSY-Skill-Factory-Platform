import type { JointAngles } from "./telemetryTypes";

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

/** Map joint angles in radians to Phase 0 `joints_deg` (string keys). */
export function jointRadMapToJointsDeg(joints: JointAngles): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, rad] of Object.entries(joints)) {
    if (typeof rad === "number" && Number.isFinite(rad)) {
      out[k] = rad * RAD2DEG;
    }
  }
  return out;
}

export type BuildKeyframesOptions = {
  schemaVersion?: string;
  robotModel?: string;
  timestampS?: number;
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
  const joints_deg = jointRadMapToJointsDeg(jointsRad);
  return {
    schema_version,
    robot_model,
    units: { angle: "degrees", time: "seconds" },
    keyframes: [{ timestamp_s, joints_deg }],
  };
}

export function stringifyKeyframesDocument(doc: Record<string, unknown>): string {
  return `${JSON.stringify(doc, null, 2)}\n`;
}
