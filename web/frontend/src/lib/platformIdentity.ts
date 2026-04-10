export const PLATFORM_USER_STORAGE_KEY = "g1_platform_user_id";

/** Typical dev default when backend omits header; see G1_DEV_USER_ID in backend config. */
export const DEFAULT_PLATFORM_USER_ID = "local-dev";

function readStoredOverride(): string | null {
  try {
    const v = localStorage.getItem(PLATFORM_USER_STORAGE_KEY);
    if (v === null) return null;
    const t = v.trim();
    return t === "" ? null : t;
  } catch {
    return null;
  }
}

/** Effective user id for Phase 5: localStorage override → VITE_PLATFORM_USER_ID → default. */
export function getPlatformUserId(): string {
  const stored = readStoredOverride();
  if (stored !== null) return stored;
  const fromEnv = (import.meta.env.VITE_PLATFORM_USER_ID ?? "").trim();
  if (fromEnv) return fromEnv;
  return DEFAULT_PLATFORM_USER_ID;
}

/** Persist override in localStorage; empty or whitespace-only clears override (env/default apply). */
export function setStoredPlatformUserId(raw: string): void {
  const t = raw.trim();
  try {
    if (t === "") {
      localStorage.removeItem(PLATFORM_USER_STORAGE_KEY);
    } else {
      localStorage.setItem(PLATFORM_USER_STORAGE_KEY, t);
    }
  } catch {
    /* private mode / SSR */
  }
}

export function clearStoredPlatformUserId(): void {
  try {
    localStorage.removeItem(PLATFORM_USER_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** Path without query string, leading slash. */
export function isPlatformPhase5Path(pathWithoutQuery: string): boolean {
  const p = pathWithoutQuery.startsWith("/") ? pathWithoutQuery : `/${pathWithoutQuery}`;
  if (p.startsWith("/api/platform/")) return true;
  if (p === "/api/jobs" || p.startsWith("/api/jobs/")) return true;
  if (p === "/api/packages" || p.startsWith("/api/packages/")) return true;
  return false;
}
