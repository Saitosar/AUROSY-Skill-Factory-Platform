import { describe, expect, it } from "vitest";
import { qposToSkillJointAngles, qposVecGet, qposVecSet } from "./qposToSkillAngles";

describe("qposToSkillJointAngles", () => {
  it("reads hinge angles by joint name (excludes floating base)", () => {
    const qpos = new Float64Array(64);
    qpos.fill(0);
    const model = {
      jnt(name: string) {
        const adr: Record<string, number> = {
          left_hip_pitch_joint: 7,
          right_wrist_yaw_joint: 12,
        };
        const a = adr[name];
        if (a === undefined) throw new Error(`unknown ${name}`);
        return { qposadr: a };
      },
    };
    qpos[7] = 0.25;
    qpos[12] = -0.1;
    const angles = qposToSkillJointAngles(model, { qpos });
    expect(angles.left_hip_pitch).toBe(0.25);
    expect(angles.right_wrist_yaw).toBe(-0.1);
  });

  it("qposVecGet/Set support mjDoubleVec-like objects (MuJoCo WASM)", () => {
    const store = new Map<number, number>();
    const vec = {
      get: (i: number) => store.get(i),
      set: (i: number, v: number) => {
        store.set(i, v);
        return true;
      },
    };
    qposVecSet(vec, 3, 1.25);
    expect(qposVecGet(vec, 3)).toBe(1.25);
  });
});
