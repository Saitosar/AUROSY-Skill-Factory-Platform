import { describe, expect, it } from "vitest";
import {
  MENAGERIE_JOINT_NAMES,
  SKILL_KEYS_IN_JOINT_MAP_ORDER,
  menagerieJointToSkillKey,
} from "./jointMapping";

describe("jointMapping", () => {
  it("has 29 joints matching G1 control map", () => {
    expect(MENAGERIE_JOINT_NAMES).toHaveLength(29);
    expect(SKILL_KEYS_IN_JOINT_MAP_ORDER).toHaveLength(29);
  });

  it("strips _joint suffix for Skill Foundry keys", () => {
    expect(menagerieJointToSkillKey("left_hip_pitch_joint")).toBe("left_hip_pitch");
    expect(menagerieJointToSkillKey("waist_yaw_joint")).toBe("waist_yaw");
  });

  it("matches documented Phase 0 order (sample)", () => {
    expect(SKILL_KEYS_IN_JOINT_MAP_ORDER[0]).toBe("left_hip_pitch");
    expect(SKILL_KEYS_IN_JOINT_MAP_ORDER[12]).toBe("waist_yaw");
    expect(SKILL_KEYS_IN_JOINT_MAP_ORDER[28]).toBe("right_wrist_yaw");
  });
});
