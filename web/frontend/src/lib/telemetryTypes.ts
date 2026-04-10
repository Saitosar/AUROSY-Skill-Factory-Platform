/** Joint angle map: keys are string indices "0"…"28" as sent by the backend. */
export type JointAngles = Record<string, number>;

/**
 * WebSocket telemetry frame. Mock sends at least `timestamp_s`, `joints`, optional `mock`.
 * Optional second set for goal vs actual — names may vary; we accept common aliases.
 */
export type TelemetryFrame = {
  timestamp_s: number;
  joints: JointAngles;
  mock?: boolean;
  /** Goal / commanded angles when present alongside `joints` as actual state */
  target_joints?: JointAngles;
  command_joints?: JointAngles;
  type?: string;
};

const TARGET_KEYS = ["target_joints", "command_joints"] as const;

/** Parse a JSON object into TelemetryFrame if it has `joints`; otherwise null. */
export function parseTelemetryMessage(data: unknown): TelemetryFrame | null {
  if (!data || typeof data !== "object") return null;
  const o = data as Record<string, unknown>;
  if (!o.joints || typeof o.joints !== "object") return null;
  const joints = o.joints as Record<string, unknown>;
  const out: JointAngles = {};
  for (const [k, v] of Object.entries(joints)) {
    if (typeof v === "number" && Number.isFinite(v)) out[k] = v;
  }
  if (Object.keys(out).length === 0) return null;
  const ts = o.timestamp_s;
  const timestamp_s = typeof ts === "number" && Number.isFinite(ts) ? ts : 0;
  const frame: TelemetryFrame = {
    timestamp_s,
    joints: out,
  };
  if (typeof o.mock === "boolean") frame.mock = o.mock;
  if (typeof o.type === "string") frame.type = o.type;
  for (const key of TARGET_KEYS) {
    const raw = o[key];
    if (!raw || typeof raw !== "object") continue;
    const tgt: JointAngles = {};
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      if (typeof v === "number" && Number.isFinite(v)) tgt[k] = v;
    }
    if (Object.keys(tgt).length > 0) {
      if (key === "target_joints") frame.target_joints = tgt;
      else frame.command_joints = tgt;
    }
  }
  return frame;
}

/** Prefer explicit target_joints, else command_joints. */
export function getTargetAngles(frame: TelemetryFrame): JointAngles | undefined {
  return frame.target_joints ?? frame.command_joints;
}

export const JOINT_SLIDER_RAD_MIN = -Math.PI;
export const JOINT_SLIDER_RAD_MAX = Math.PI;
