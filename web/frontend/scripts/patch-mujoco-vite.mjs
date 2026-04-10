/**
 * Idempotent patch: Emscripten pthread stubs in @mujoco/mujoco confuse Vite 5 worker
 * static analysis. Inserts the vite-ignore comment recommended by Vite's error message.
 * Run automatically from postinstall.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const target = path.join(__dirname, "..", "node_modules", "@mujoco", "mujoco", "mujoco.js");

if (!fs.existsSync(target)) {
  process.stderr.write("patch-mujoco-vite: @mujoco/mujoco not installed, skip\n");
  process.exit(0);
}

let s = fs.readFileSync(target, "utf8");
const a = `worker = new Worker(pthreadMainJs, {\n        /* @vite-ignore */\n        "type": "module",`;
const b = `worker = new Worker(new URL("mujoco.js", import.meta.url), {\n      /* @vite-ignore */\n      "type": "module",`;

if (s.includes("/* @vite-ignore */") && s.includes('worker = new Worker(pthreadMainJs')) {
  process.stdout.write("patch-mujoco-vite: already patched\n");
  process.exit(0);
}

s = s.replace(
  /worker = new Worker\(pthreadMainJs, \{\s*\n\s*"type": "module",/,
  a
);
s = s.replace(
  /worker = new Worker\(new URL\("mujoco\.js", import\.meta\.url\), \{\s*\n\s*"type": "module",/,
  b
);

if (!s.includes("/* @vite-ignore */")) {
  process.stderr.write("patch-mujoco-vite: pattern mismatch, manual check needed\n");
  process.exit(1);
}

fs.writeFileSync(target, s);
process.stdout.write("patch-mujoco-vite: patched " + target + "\n");
