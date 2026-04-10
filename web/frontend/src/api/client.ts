import { getPlatformUserId, isPlatformPhase5Path } from "@/lib/platformIdentity";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export {
  clearStoredPlatformUserId,
  getPlatformUserId,
  isPlatformPhase5Path,
  setStoredPlatformUserId,
} from "@/lib/platformIdentity";

/** Fetch with `apiUrl(path)`; adds `X-User-Id` for Phase 5 routes unless already set. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const pathOnly = (path.split("?")[0] || path).trim();
  const normalized = pathOnly.startsWith("/") ? pathOnly : `/${pathOnly}`;
  const headers = new Headers(init?.headers);
  if (isPlatformPhase5Path(normalized) && !headers.has("X-User-Id")) {
    headers.set("X-User-Id", getPlatformUserId());
  }
  return fetch(apiUrl(path), { ...init, headers });
}

/** Raw `VITE_API_BASE` from env (trimmed); empty means same-origin / Vite proxy in dev. */
export function getConfiguredApiBase(): string {
  return (import.meta.env.VITE_API_BASE ?? "").trim();
}

/** REST paths; when VITE_API_BASE is set, requests go to that origin (no trailing slash). */
export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  if (!API_BASE) return p;
  return `${API_BASE.replace(/\/$/, "")}${p}`;
}

function errorBodyMessage(r: Response, text: string): string {
  const trimmed = text.trim();
  if (r.status === 503 || r.status === 502 || r.status === 504) {
    try {
      const j = JSON.parse(trimmed) as { detail?: string };
      if (typeof j.detail === "string" && j.detail.trim()) return j.detail.trim();
    } catch {
      /* use trimmed */
    }
  }
  return trimmed || `${r.status} ${r.statusText}`.trim();
}

export async function getHealth(): Promise<{ status: string }> {
  const r = await fetch(apiUrl("/api/health"));
  const text = await r.text();
  if (!r.ok) throw new Error(errorBodyMessage(r, text));
  try {
    return JSON.parse(text) as { status: string };
  } catch {
    throw new Error(`Invalid JSON from /api/health: ${text.slice(0, 120)}`);
  }
}

/** Response of `GET /api/meta`; optional fields appear when the backend exposes them (see OpenAPI). */
export type ApiMetaResponse = {
  repo_root: string;
  sdk_python_root: string;
  mjcf_default: string | null;
  telemetry_mode: string;
  /** When present: whether the Phase 5 queue worker loop is enabled on the server. */
  platform_worker_enabled?: boolean | null;
  /** When present: server-side job time limit in seconds (name may match backend config e.g. `job_timeout_sec`). */
  job_timeout_sec?: number | null;
  /**
   * When true, Motion Studio telemetry mode may send joint targets via `POST /api/joints/targets`
   * (see `web/backend/joint_command_router.py` in this repo for an integration snippet).
   */
  joint_command_enabled?: boolean | null;
};

export async function getMeta() {
  const r = await fetch(apiUrl("/api/meta"));
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<ApiMetaResponse>;
}

export async function getJoints() {
  const r = await fetch(apiUrl("/api/joints"));
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    joint_map: Record<string, string>;
    groups: { name: string; indices: number[] }[];
  }>;
}

/** Joint index string keys "0"…"28" → angle in degrees (matches Phase 0 / Python pose.json). */
export type JointTargetsDegPayload = {
  joints_deg: Record<string, number>;
};

/**
 * Send commanded joint angles (degrees) to the backend for forwarding to DDS / sim (when enabled).
 * @throws if the route is missing (404) or the server rejects the body
 */
export async function postJointTargets(body: JointTargetsDegPayload) {
  const r = await apiFetch("/api/joints/targets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ ok?: boolean }>;
}

/** Request passive / release semantics for joint holding (backend integrator defines behavior). */
export async function postJointRelease() {
  const r = await apiFetch("/api/joints/release", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ ok?: boolean }>;
}

export async function validateApi(
  kind:
    | "keyframes"
    | "motion"
    | "scenario"
    | "reference_trajectory"
    | "demonstration_dataset",
  payload: unknown
) {
  const r = await fetch(apiUrl("/api/validate"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, payload }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ ok: boolean; errors: string[] }>;
}

export async function getMidLevelActions() {
  const r = await fetch(apiUrl("/api/mid-level/actions"));
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    actions: {
      subdir: string;
      action_name: string;
      label: string;
      keyframe_count: number;
    }[];
  }>;
}

export async function estimateScenario(nodes: unknown) {
  const r = await fetch(apiUrl("/api/scenario/estimate"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nodes }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    nodes: {
      subdir: string;
      action_name: string;
      speed: number;
      repeat: number;
      keyframe_count: number;
      estimated_seconds: number;
    }[];
    total_estimated_seconds: number;
  }>;
}

export type PreprocessPipelineResponse = {
  exit_code: number;
  stdout: string;
  stderr: string;
  reference_trajectory_json: string | null;
  preprocess_run_json: string | null;
};

/** Ответы playback/train: subprocess-поля + произвольные поля артефактов (см. OpenAPI бэкенда). */
export type PipelineSubprocessJsonResult = {
  exit_code?: number;
  stdout?: string;
  stderr?: string;
} & Record<string, unknown>;

export type PlaybackRequestBody = {
  mjcf_path?: string | null;
  reference_path?: string;
  reference_trajectory?: unknown;
  mode?: string;
  write_demonstration_json?: boolean;
  max_steps?: number;
};

export type TrainRequestBody = {
  mode?: string;
  reference_path?: string;
  config_path?: string;
};

export async function runPreprocess(
  keyframes: unknown,
  frequency_hz?: number
): Promise<PreprocessPipelineResponse> {
  const r = await fetch(apiUrl("/api/pipeline/preprocess"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keyframes, frequency_hz: frequency_hz ?? null }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<PreprocessPipelineResponse>;
}

export async function runPlayback(body: PlaybackRequestBody): Promise<PipelineSubprocessJsonResult> {
  const r = await fetch(apiUrl("/api/pipeline/playback"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<PipelineSubprocessJsonResult>;
}

export async function runTrain(body: TrainRequestBody): Promise<PipelineSubprocessJsonResult> {
  const r = await fetch(apiUrl("/api/pipeline/train"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<PipelineSubprocessJsonResult>;
}

export async function getCliDetection() {
  const r = await fetch(apiUrl("/api/pipeline/detect-cli"));
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    commands: { preprocess: string | null; playback: string | null; train: string | null };
  }>;
}

// --- Phase 5: platform artifacts & async train jobs (F14; bodies per OpenAPI backend) ---

export type TrainJobEnqueueBody = {
  mode: "smoke" | "train";
  /** Optional; server defaults to `{}` and merges `output_dir` into train_config.json. */
  config?: Record<string, unknown>;
  /** Mutually exclusive with reference_artifact on the server; send only one. */
  reference_trajectory?: unknown;
  reference_artifact?: string;
  /** Mutually exclusive with demonstration_artifact; send only one. */
  demonstration_dataset?: unknown;
  demonstration_artifact?: string;
};

/** Normalized job id from list/detail responses (backend may use job_id or id). */
export function platformJobId(row: Record<string, unknown>): string {
  const a = row.job_id;
  const b = row.id;
  if (typeof a === "string" && a) return a;
  if (typeof b === "string" && b) return b;
  return "";
}

export type PlatformJobSummary = {
  job_id?: string;
  id?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
} & Record<string, unknown>;

export type PlatformJobDetail = PlatformJobSummary & {
  exit_code?: number | null;
  stdout_tail?: string | null;
  stderr_tail?: string | null;
};

function parseJobsListPayload(data: unknown): PlatformJobSummary[] {
  if (Array.isArray(data)) return data as PlatformJobSummary[];
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>;
    for (const key of ["jobs", "items", "results"]) {
      const v = o[key];
      if (Array.isArray(v)) return v as PlatformJobSummary[];
    }
  }
  return [];
}

/** Prefer JSON detail/message from an already-read error body. */
export function parseApiErrorText(text: string, status: number, statusText: string): string {
  try {
    const j = JSON.parse(text) as Record<string, unknown>;
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) return JSON.stringify(j.detail);
    if (typeof j.message === "string") return j.message;
    if (typeof j.error === "string") return j.error;
    return text || `${status} ${statusText}`;
  } catch {
    return text || `${status} ${statusText}`;
  }
}

/** Non-OK response: prefer JSON detail/message, else raw text. */
export async function readApiErrorMessage(r: Response): Promise<string> {
  const text = await r.text();
  return parseApiErrorText(text, r.status, r.statusText);
}

/** 409 from PATCH package publish: keep structured body for UI (validation gate, etc.). */
export class PackagePublishConflictError extends Error {
  readonly body: unknown;

  constructor(message: string, body: unknown) {
    super(message);
    this.name = "PackagePublishConflictError";
    this.body = body;
  }
}

/** Human-readable summary; falls back to JSON so server fields are never dropped. */
export function formatPackagePublishConflictBody(body: unknown): string {
  if (body === null || body === undefined) return "";
  if (typeof body === "string") return body;
  if (typeof body === "object" && !Array.isArray(body)) {
    const o = body as Record<string, unknown>;
    const lines: string[] = [];
    if (typeof o.detail === "string") lines.push(o.detail);
    if ("validation_passed" in o) lines.push(`validation_passed: ${String(o.validation_passed)}`);
    if (Array.isArray(o.failure_reasons)) {
      for (const x of o.failure_reasons) lines.push(String(x));
    } else if (typeof o.failure_reasons === "string") {
      lines.push(o.failure_reasons);
    }
    if (lines.length > 0) return lines.join("\n");
  }
  try {
    return JSON.stringify(body, null, 2);
  } catch {
    return String(body);
  }
}

function parseJsonConflictBody(text: string): unknown {
  const t = text.trim();
  if (!t) return {};
  try {
    return JSON.parse(t) as unknown;
  } catch {
    return text;
  }
}

export type PoseDraftSaveBody = {
  name: string;
  document: Record<string, unknown>;
};

/** Saves keyframes JSON under the user's `pose_drafts/` workspace (Phase 5). */
export async function savePoseDraft(body: PoseDraftSaveBody): Promise<{ path: string }> {
  const r = await apiFetch("/api/platform/pose-drafts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiErrorMessage(r));
  return (await r.json()) as { path: string };
}

export async function savePlatformArtifact(name: string, payload: unknown): Promise<unknown> {
  const path = `/api/platform/artifacts/${encodeURIComponent(name)}`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(await readApiErrorMessage(r));
  const text = await r.text();
  if (!text.trim()) return {};
  return JSON.parse(text) as unknown;
}

export async function enqueueTrainJob(body: TrainJobEnqueueBody): Promise<{ job_id: string }> {
  const r = await apiFetch("/api/jobs/train", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await r.text();
  if (!r.ok) throw new Error(await readApiErrorMessage(r));
  const json = JSON.parse(text) as Record<string, unknown>;
  const job_id =
    (typeof json.job_id === "string" && json.job_id) ||
    (typeof json.id === "string" && json.id) ||
    "";
  if (!job_id) throw new Error(text || "enqueue: missing job id in response");
  return { job_id };
}

export async function listJobs(): Promise<PlatformJobSummary[]> {
  const r = await apiFetch("/api/jobs");
  if (!r.ok) throw new Error(await readApiErrorMessage(r));
  const data = (await r.json()) as unknown;
  return parseJobsListPayload(data);
}

export async function getJob(jobId: string): Promise<PlatformJobDetail> {
  const r = await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}`);
  if (!r.ok) throw new Error(await readApiErrorMessage(r));
  return r.json() as Promise<PlatformJobDetail>;
}

/** Stop polling when backend reports a finished state (extend if OpenAPI adds values). */
export function isTerminalJobStatus(status: string | undefined): boolean {
  if (!status) return false;
  const s = status.toLowerCase();
  return (
    s === "succeeded" ||
    s === "success" ||
    s === "completed" ||
    s === "failed" ||
    s === "error" ||
    s === "cancelled" ||
    s === "canceled"
  );
}

/** Successful train job — eligible for Skill Bundle packaging (F15). */
export function isSucceededJobStatus(status: string | undefined): boolean {
  if (!status) return false;
  const s = status.toLowerCase();
  return s === "succeeded" || s === "success" || s === "completed";
}

// --- Phase 5: Skill Bundle packages (F15) ---

export type PlatformPackageRow = {
  package_id?: string;
  id?: string;
  label?: string;
  published?: boolean;
  created_at?: string;
  validation_passed?: boolean;
  failure_reasons?: string[] | string;
} & Record<string, unknown>;

function parsePackagesListPayload(data: unknown): PlatformPackageRow[] {
  if (Array.isArray(data)) return data as PlatformPackageRow[];
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>;
    for (const key of ["packages", "items", "results"]) {
      const v = o[key];
      if (Array.isArray(v)) return v as PlatformPackageRow[];
    }
  }
  return [];
}

export function platformPackageId(row: Record<string, unknown>): string {
  const a = row.package_id;
  const b = row.id;
  if (typeof a === "string" && a) return a;
  if (typeof b === "string" && b) return b;
  return "";
}

export async function listPackages(): Promise<PlatformPackageRow[]> {
  const r = await apiFetch("/api/packages");
  if (!r.ok) throw new Error(await readApiErrorMessage(r));
  const data = (await r.json()) as unknown;
  return parsePackagesListPayload(data);
}

export async function createPackageFromJob(jobId: string): Promise<{ package_id: string }> {
  const path = `/api/packages/from-job/${encodeURIComponent(jobId)}`;
  const r = await apiFetch(path, { method: "POST" });
  const text = await r.text();
  if (!r.ok) throw new Error(parseApiErrorText(text, r.status, r.statusText));
  const json = (text.trim() ? JSON.parse(text) : {}) as Record<string, unknown>;
  const package_id =
    (typeof json.package_id === "string" && json.package_id) ||
    (typeof json.id === "string" && json.id) ||
    "";
  if (!package_id) throw new Error(text || "package: missing package id in response");
  return { package_id };
}

const DEFAULT_BUNDLE_FILENAME = "skill_bundle.tar.gz";

function filenameFromContentDisposition(cd: string | null): string | null {
  if (!cd) return null;
  const star = /filename\*=UTF-8''([^;\n]+)/i.exec(cd);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"+|"+$/g, ""));
    } catch {
      return star[1].trim().replace(/^"+|"+$/g, "");
    }
  }
  const plain = /filename="([^"]+)"/i.exec(cd) || /filename=([^;\s]+)/i.exec(cd);
  if (plain?.[1]) return plain[1].trim().replace(/^"+|"+$/g, "");
  return null;
}

export async function downloadSkillBundle(
  packageId: string
): Promise<{ blob: Blob; filename: string }> {
  const r = await apiFetch(`/api/packages/${encodeURIComponent(packageId)}/download`);
  if (!r.ok) throw new Error(await readApiErrorMessage(r));
  const blob = await r.blob();
  const filename =
    filenameFromContentDisposition(r.headers.get("Content-Disposition")) ?? DEFAULT_BUNDLE_FILENAME;
  return { blob, filename };
}

/** Multipart upload; field name `file` (FastAPI typical — confirm in backend OpenAPI). */
export async function uploadSkillBundle(file: File): Promise<unknown> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await apiFetch("/api/packages/upload", { method: "POST", body: fd });
  const text = await r.text();
  if (!r.ok) throw new Error(parseApiErrorText(text, r.status, r.statusText));
  if (!text.trim()) return {};
  return JSON.parse(text) as unknown;
}

export async function setPackagePublished(packageId: string, published: boolean): Promise<void> {
  const r = await apiFetch(`/api/packages/${encodeURIComponent(packageId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ published }),
  });
  const text = await r.text();
  if (r.ok) return;
  if (r.status === 409) {
    const body = parseJsonConflictBody(text);
    throw new PackagePublishConflictError(formatPackagePublishConflictBody(body), body);
  }
  throw new Error(parseApiErrorText(text, r.status, r.statusText));
}

/** WebSocket URL for joint telemetry; follows VITE_API_BASE when set. */
export function telemetryWebSocketUrl(): string {
  if (!API_BASE) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws/telemetry`;
  }
  const u = new URL(API_BASE);
  const wsProto = u.protocol === "https:" ? "wss:" : "ws:";
  return `${wsProto}//${u.host}/ws/telemetry`;
}
