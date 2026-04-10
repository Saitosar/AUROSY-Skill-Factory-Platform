import type { JointAngles } from "../lib/telemetryTypes";
import { MENAGERIE_JOINT_NAMES, menagerieJointToSkillKey } from "./jointMapping";

/** Embind may expose scalars as plain numbers or wrappers. */
function asNumber(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (v != null && typeof v === "object" && "value" in v) {
    const n = Number((v as { value: unknown }).value);
    if (Number.isFinite(n)) return n;
  }
  return Number(v);
}

type MinimalMjModel = {
  jnt(name: string): { qposadr: unknown; range?: Float64Array | Float32Array };
};

type MinimalMjData = {
  /** MuJoCo WASM uses `mjDoubleVec` with `.get/.set`; tests may use a typed array. */
  qpos: unknown;
};

function isMjDoubleVecLike(
  qpos: unknown
): qpos is { get: (i: number) => number | undefined; set: (i: number, v: number) => boolean } {
  return (
    qpos != null &&
    typeof qpos === "object" &&
    typeof (qpos as { get?: unknown }).get === "function" &&
    typeof (qpos as { set?: unknown }).set === "function"
  );
}

/** Read one `qpos` entry (WASM `mjDoubleVec` or JS `Float64Array`). */
export function qposVecGet(qpos: unknown, adr: number): number | undefined {
  if (adr < 0) return undefined;
  if (isMjDoubleVecLike(qpos)) {
    const v = qpos.get(adr);
    return typeof v === "number" && Number.isFinite(v) ? v : undefined;
  }
  const arr = qpos as ArrayLike<number>;
  const v = arr[adr];
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

/** Write one `qpos` entry (required for WASM — bracket assignment does not hit the native buffer). */
export function qposVecSet(qpos: unknown, adr: number, v: number): void {
  if (adr < 0 || !Number.isFinite(v)) return;
  if (isMjDoubleVecLike(qpos)) {
    qpos.set(adr, v);
    return;
  }
  (qpos as Float64Array | Float32Array)[adr] = v;
}

/**
 * Reads hinge joint angles (rad) from MuJoCo state using the same Skill Foundry
 * keys as `GET /api/joints` / Phase 0 keyframes (excludes floating base).
 */
export function qposToSkillJointAngles(model: MinimalMjModel, data: MinimalMjData): JointAngles {
  const qpos = data.qpos;
  const out: JointAngles = {};
  for (const mjName of MENAGERIE_JOINT_NAMES) {
    try {
      const ja = model.jnt(mjName);
      const adr = asNumber(ja.qposadr);
      const v = qposVecGet(qpos, adr);
      if (typeof v === "number" && Number.isFinite(v)) {
        out[menagerieJointToSkillKey(mjName)] = v;
      }
    } catch {
      /* missing joint in this MJCF */
    }
  }
  return out;
}

export function skillKeyQposAddress(model: MinimalMjModel, skillKey: string): number {
  const mjName = `${skillKey}_joint`;
  try {
    const ja = model.jnt(mjName);
    return asNumber(ja.qposadr);
  } catch {
    return -1;
  }
}

export function jointRangeRad(model: MinimalMjModel, skillKey: string): { min: number; max: number } | null {
  const mjName = `${skillKey}_joint`;
  try {
    const ja = model.jnt(mjName);
    const r = ja.range as Float64Array | Float32Array | undefined;
    if (r && r.length >= 2) {
      const a = r[0];
      const b = r[1];
      if (Number.isFinite(a) && Number.isFinite(b)) return { min: a, max: b };
    }
  } catch {
    /* unknown joint */
  }
  return null;
}
