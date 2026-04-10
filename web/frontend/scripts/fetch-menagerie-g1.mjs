/**
 * Downloads Unitree G1 MJCF + meshes from DeepMind mujoco_menagerie (BSD-3-Clause).
 * Run: node scripts/fetch-menagerie-g1.mjs
 * Output: public/mujoco/g1/
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, "..");
const OUT = path.join(ROOT, "public", "mujoco", "g1");
const BASE =
  "https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/main/unitree_g1";

const STL = [
  "head_link.STL",
  "left_ankle_pitch_link.STL",
  "left_ankle_roll_link.STL",
  "left_elbow_link.STL",
  "left_hip_pitch_link.STL",
  "left_hip_roll_link.STL",
  "left_hip_yaw_link.STL",
  "left_knee_link.STL",
  "left_rubber_hand.STL",
  "left_shoulder_pitch_link.STL",
  "left_shoulder_roll_link.STL",
  "left_shoulder_yaw_link.STL",
  "left_wrist_pitch_link.STL",
  "left_wrist_roll_link.STL",
  "left_wrist_yaw_link.STL",
  "logo_link.STL",
  "pelvis.STL",
  "pelvis_contour_link.STL",
  "right_ankle_pitch_link.STL",
  "right_ankle_roll_link.STL",
  "right_elbow_link.STL",
  "right_hip_pitch_link.STL",
  "right_hip_roll_link.STL",
  "right_hip_yaw_link.STL",
  "right_knee_link.STL",
  "right_rubber_hand.STL",
  "right_shoulder_pitch_link.STL",
  "right_shoulder_roll_link.STL",
  "right_shoulder_yaw_link.STL",
  "right_wrist_pitch_link.STL",
  "right_wrist_roll_link.STL",
  "right_wrist_yaw_link.STL",
  "torso_link_rev_1_0.STL",
  "waist_roll_link_rev_1_0.STL",
  "waist_yaw_link_rev_1_0.STL",
];

async function fetchBuf(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return Buffer.from(await r.arrayBuffer());
}

/** Avoid pthread/Web Worker storm during MJCF compile (EAGAIN on some macOS hosts). */
function patchMujocoXmlForBrowserCompile(xml) {
  const s = xml.toString("utf8");
  if (/\bcompiler\b[^>]*\busethread\s*=/i.test(s)) return s;
  if (/<compiler\b/i.test(s)) {
    return s.replace(/<compiler\b([^>]*?)(\/>|>)/gi, (full, attrs, close) => {
      if (/\busethread\s*=/.test(attrs)) return full;
      return `<compiler${attrs} usethread="false"${close}`;
    });
  }
  return s.replace(/<mujoco\b[^>]*>/i, (open) => `${open}\n  <compiler usethread="false"/>`);
}

async function main() {
  fs.mkdirSync(path.join(OUT, "assets"), { recursive: true });

  for (const name of ["scene.xml", "g1.xml"]) {
    const url = `${BASE}/${name}`;
    process.stdout.write(`fetch ${name}\n`);
    const buf = await fetchBuf(url);
    let body = buf;
    if (name.endsWith(".xml")) {
      body = Buffer.from(patchMujocoXmlForBrowserCompile(buf), "utf8");
    }
    fs.writeFileSync(path.join(OUT, name), body);
  }

  for (const stl of STL) {
    const url = `${BASE}/assets/${stl}`;
    process.stdout.write(`fetch assets/${stl}\n`);
    const buf = await fetchBuf(url);
    fs.writeFileSync(path.join(OUT, "assets", stl), buf);
  }

  process.stdout.write(`Done. Wrote to ${OUT}\n`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
