import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { PipelineSubprocessJsonResult, PreprocessPipelineResponse } from "../api/client";

export const MAX_PIPELINE_PREVIEW_CHARS = 8000;

function truncateText(s: string, max: number, truncatedMsg: string): { text: string; truncated: boolean } {
  if (s.length <= max) return { text: s, truncated: false };
  return { text: `${s.slice(0, max)}\n${truncatedMsg}`, truncated: true };
}

export function TruncatedBlock({
  title,
  value,
  maxChars = MAX_PIPELINE_PREVIEW_CHARS,
}: {
  title: string;
  value: string;
  maxChars?: number;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const { display, showToggle } = useMemo(() => {
    if (expanded) return { display: value, showToggle: value.length > maxChars };
    const truncatedLine = t("pipelineOutput.truncated", { count: value.length });
    const { text, truncated } = truncateText(value, maxChars, truncatedLine);
    return { display: text, showToggle: truncated };
  }, [value, expanded, maxChars, t]);

  return (
    <div className="pipeline-log-block">
      <div className="pipeline-log-block-title">{title}</div>
      <pre className="logbox pipeline-log-pre">{display}</pre>
      {showToggle && (
        <button
          type="button"
          className="secondary pipeline-log-expand"
          onClick={() => setExpanded((e) => !e)}
        >
          {expanded ? t("pipelineOutput.collapse") : t("pipelineOutput.expand")}
        </button>
      )}
    </div>
  );
}

function restObjectForJsonView(obj: PipelineSubprocessJsonResult): Record<string, unknown> {
  const skip = new Set(["exit_code", "stdout", "stderr"]);
  const rest: Record<string, unknown> = {};
  for (const k of Object.keys(obj)) {
    if (!skip.has(k)) rest[k] = obj[k];
  }
  return rest;
}

export function PipelineSubprocessResultView({ result }: { result: PipelineSubprocessJsonResult }) {
  const { t } = useTranslation();
  const rest = restObjectForJsonView(result);
  const restKeys = Object.keys(rest);
  const restString = restKeys.length > 0 ? JSON.stringify(rest, null, 2) : "";
  const hasStdio =
    "stdout" in result && typeof result.stdout === "string"
      ? true
      : "stderr" in result && typeof result.stderr === "string";
  const showRawFallback =
    !("exit_code" in result) && !hasStdio && restKeys.length === 0;

  return (
    <div className="pipeline-log-stack">
      {"exit_code" in result && typeof result.exit_code === "number" && (
        <div className="pipeline-exit-code muted">
          exit_code: <strong>{result.exit_code}</strong>
        </div>
      )}
      {"stdout" in result && typeof result.stdout === "string" && (
        <TruncatedBlock title="stdout" value={result.stdout} />
      )}
      {"stderr" in result && typeof result.stderr === "string" && (
        <TruncatedBlock title="stderr" value={result.stderr} />
      )}
      {restString && <TruncatedBlock title={t("pipelineOutput.titleRestJson")} value={restString} />}
      {showRawFallback && (
        <TruncatedBlock title={t("pipelineOutput.titleResponseJson")} value={JSON.stringify(result, null, 2)} />
      )}
    </div>
  );
}

export function PreprocessResultView({ result }: { result: PreprocessPipelineResponse }) {
  const { t } = useTranslation();
  return (
    <div className="pipeline-log-stack">
      <div className="pipeline-exit-code muted">
        exit_code: <strong>{result.exit_code}</strong>
      </div>
      <TruncatedBlock title="stdout" value={result.stdout} />
      <TruncatedBlock title="stderr" value={result.stderr} />
      {result.reference_trajectory_json && (
        <TruncatedBlock
          title={t("pipelineOutput.titleRefTrajectory")}
          value={result.reference_trajectory_json}
        />
      )}
      {!result.reference_trajectory_json && (
        <p className="muted" style={{ margin: 0 }}>
          {t("pipelineOutput.refMissing")}
        </p>
      )}
      {result.preprocess_run_json && (
        <TruncatedBlock title={t("pipelineOutput.titlePreprocessRun")} value={result.preprocess_run_json} />
      )}
    </div>
  );
}

export function ErrorWithExpand({ message }: { message: string }) {
  const { t } = useTranslation();
  return <TruncatedBlock title={t("pipelineOutput.titleError")} value={message} maxChars={4000} />;
}
