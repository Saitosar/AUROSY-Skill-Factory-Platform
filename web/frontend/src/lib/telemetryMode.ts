/**
 * Whether `/api/meta` reports DDS-backed telemetry (WebSocket may fail if the DDS bridge is not deployed).
 * Typical backend value: `"dds"` (case-insensitive) when DDS is selected (e.g. `G1_USE_DDS_TELEMETRY=1`).
 * Confirm allowed values in the backend OpenAPI / README.
 */
export function isDdsTelemetryMode(mode: string | undefined | null): boolean {
  if (mode == null || typeof mode !== "string") return false;
  return mode.trim().toLowerCase() === "dds";
}
