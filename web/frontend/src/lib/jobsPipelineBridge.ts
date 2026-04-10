/** React Router location.state key: reference trajectory from Pipeline preprocess → Jobs prefill. */
export const PIPELINE_REF_TRAJECTORY_STATE_KEY = "pipelineRefTrajectory";

export function extractPipelineRefFromLocationState(state: unknown): unknown | null {
  if (!state || typeof state !== "object") return null;
  const v = (state as Record<string, unknown>)[PIPELINE_REF_TRAJECTORY_STATE_KEY];
  return v === undefined ? null : v;
}
