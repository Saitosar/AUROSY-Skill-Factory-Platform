/**
 * When the Vite dev proxy cannot reach http://127.0.0.1:8000, http-proxy would emit an
 * empty HTTP 500. We respond with 503 + JSON so the UI and DevTools show a clear reason.
 */
export function attachBackendProxyErrorHandler(proxy: {
  on(event: "error", cb: (...args: unknown[]) => void): void;
}): void {
  proxy.on("error", (_err, _req, res) => {
    const r = res as {
      headersSent?: boolean;
      writeHead?: (code: number, headers: Record<string, string>) => void;
      end?: (body: string) => void;
    } | null;
    if (!r?.writeHead || !r.end || r.headersSent) return;
    r.writeHead(503, { "Content-Type": "application/json" });
    r.end(
      JSON.stringify({
        status: "unavailable",
        detail:
          "Skill Foundry API is not running at http://127.0.0.1:8000. Start the FastAPI backend, or use 3D MuJoCo in the browser without the API.",
      })
    );
  });
}
