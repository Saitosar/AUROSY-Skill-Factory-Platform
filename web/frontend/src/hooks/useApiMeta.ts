import { useEffect, useState } from "react";
import { getMeta, type ApiMetaResponse } from "../api/client";

let sharedPromise: Promise<ApiMetaResponse | null> | null = null;

function loadMetaOnce(): Promise<ApiMetaResponse | null> {
  if (!sharedPromise) {
    sharedPromise = getMeta().catch(() => null);
  }
  return sharedPromise;
}

/** Cached `GET /api/meta` for the SPA session (dedupes parallel mounts). */
export function useApiMeta(): ApiMetaResponse | null {
  const [meta, setMeta] = useState<ApiMetaResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    void loadMetaOnce().then((m) => {
      if (!cancelled) setMeta(m);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return meta;
}
