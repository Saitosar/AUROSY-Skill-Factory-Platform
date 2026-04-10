/**
 * MuJoCo WASM 3.5+ compiles MJCF/meshes with pthread-backed workers by default.
 * Spawning many workers can fail on macOS with:
 *   "thread constructor failed: Resource temporarily unavailable" (EAGAIN).
 * Setting compiler usethread to false keeps compilation on the main thread.
 */
export function patchMujocoXmlForBrowserCompile(xml: string): string {
  if (/\bcompiler\b[^>]*\busethread\s*=/i.test(xml)) {
    return xml;
  }
  if (/<compiler\b/i.test(xml)) {
    return xml.replace(/<compiler\b([^>]*?)(\/>|>)/gi, (full, attrs: string, close: string) => {
      if (/\busethread\s*=/.test(attrs)) return full;
      return `<compiler${attrs} usethread="false"${close}`;
    });
  }
  return xml.replace(/<mujoco\b[^>]*>/i, (open) => `${open}\n  <compiler usethread="false"/>`);
}
