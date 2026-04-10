import type { PipelineSubprocessJsonResult, PreprocessPipelineResponse } from "../api/client";

/** Subprocess finished with exit code 0. */
export function preprocessExitOk(r: PreprocessPipelineResponse): boolean {
  return r.exit_code === 0;
}

/** Playback / train: treat missing exit_code as success (HTTP OK). */
export function subprocessExitOk(r: PipelineSubprocessJsonResult): boolean {
  if (typeof r.exit_code !== "number") return true;
  return r.exit_code === 0;
}
