import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getHealth } from "../api/client";

type BackendStatus = "ok" | "down";

type Ctx = {
  status: BackendStatus;
  lastError: string | null;
  initialCheckDone: boolean;
  recheck: () => void;
};

const BackendStatusContext = createContext<Ctx | null>(null);

const POLL_MS = 20_000;

export function BackendStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BackendStatus>("ok");
  const [lastError, setLastError] = useState<string | null>(null);
  const [initialCheckDone, setInitialCheckDone] = useState(false);

  const check = useCallback(() => {
    getHealth()
      .then(() => {
        setStatus("ok");
        setLastError(null);
      })
      .catch((e: unknown) => {
        setStatus("down");
        setLastError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        setInitialCheckDone(true);
      });
  }, []);

  useEffect(() => {
    check();
    const id = window.setInterval(check, POLL_MS);
    return () => window.clearInterval(id);
  }, [check]);

  const value = useMemo(
    () => ({ status, lastError, initialCheckDone, recheck: check }),
    [status, lastError, initialCheckDone, check]
  );

  return <BackendStatusContext.Provider value={value}>{children}</BackendStatusContext.Provider>;
}

export function useBackendStatus(): Ctx {
  const v = useContext(BackendStatusContext);
  if (!v) throw new Error("useBackendStatus must be used within BackendStatusProvider");
  return v;
}
