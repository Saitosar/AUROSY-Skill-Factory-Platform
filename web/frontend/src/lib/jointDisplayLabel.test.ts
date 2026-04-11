import { describe, expect, it } from "vitest";
import en from "../locales/en.json";
import ru from "../locales/ru.json";
import { SKILL_KEYS_IN_JOINT_MAP_ORDER } from "../mujoco/jointMapping";

describe("pose.jointLabels", () => {
  it("defines every skill key in EN and RU", () => {
    const enLabels = en.pose.jointLabels;
    const ruLabels = ru.pose.jointLabels;
    expect(enLabels).toBeDefined();
    expect(ruLabels).toBeDefined();
    for (const k of SKILL_KEYS_IN_JOINT_MAP_ORDER) {
      expect(enLabels[k as keyof typeof enLabels], `en: missing ${k}`).toBeDefined();
      expect(String(enLabels[k as keyof typeof enLabels]).length).toBeGreaterThan(0);
      expect(ruLabels[k as keyof typeof ruLabels], `ru: missing ${k}`).toBeDefined();
      expect(String(ruLabels[k as keyof typeof ruLabels]).length).toBeGreaterThan(0);
    }
    expect(Object.keys(enLabels!).length).toBe(SKILL_KEYS_IN_JOINT_MAP_ORDER.length);
    expect(Object.keys(ruLabels!).length).toBe(SKILL_KEYS_IN_JOINT_MAP_ORDER.length);
  });
});
