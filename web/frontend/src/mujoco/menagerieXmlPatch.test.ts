import { describe, expect, it } from "vitest";
import { patchMujocoXmlForBrowserCompile } from "./menagerieXmlPatch";

describe("patchMujocoXmlForBrowserCompile", () => {
  it("adds usethread=false to existing compiler tag", () => {
    const xml = `<mujoco><compiler angle="radian" meshdir="assets"/>\n</mujoco>`;
    expect(patchMujocoXmlForBrowserCompile(xml)).toContain('usethread="false"');
  });

  it("injects compiler after mujoco when none present", () => {
    const xml = `<mujoco model="x">\n  <include file="g1.xml"/>\n</mujoco>`;
    const out = patchMujocoXmlForBrowserCompile(xml);
    expect(out).toMatch(/<compiler[^>]*usethread="false"/);
  });

  it("is idempotent when usethread already set", () => {
    const xml = `<mujoco><compiler usethread="false"/></mujoco>`;
    expect(patchMujocoXmlForBrowserCompile(xml)).toBe(xml);
  });
});
