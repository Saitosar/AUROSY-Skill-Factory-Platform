import { useTranslation } from "react-i18next";

export type PipelineStatusBadgeKind = "success" | "error" | "running";

function IconCheck() {
  return (
    <svg className="pipeline-status-badge-icon" width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path
        fill="currentColor"
        d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 1 1 1.06-1.06L6 11.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"
      />
    </svg>
  );
}

function IconError() {
  return (
    <svg className="pipeline-status-badge-icon" width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path
        fill="currentColor"
        d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1ZM5.28 4.97a.75.75 0 0 1 1.06 0L8 6.63l1.66-1.66a.75.75 0 1 1 1.06 1.06L9.06 7.69l1.66 1.66a.75.75 0 1 1-1.06 1.06L8 8.75 6.34 10.41a.75.75 0 0 1-1.06-1.06L6.94 7.69 5.28 6.03a.75.75 0 0 1 0-1.06Z"
      />
    </svg>
  );
}

type PipelineStatusBadgeProps = {
  kind: PipelineStatusBadgeKind;
  /** When set, overrides default label for this kind */
  label?: string;
};

export function PipelineStatusBadge({ kind, label }: PipelineStatusBadgeProps) {
  const { t } = useTranslation();
  const text =
    label ??
    (kind === "success"
      ? t("pipeline.statusDone")
      : kind === "error"
        ? t("pipeline.statusError")
        : t("pipeline.statusRunning"));

  const mod =
    kind === "success" ? "pipeline-status-badge--success" : kind === "error" ? "pipeline-status-badge--error" : "pipeline-status-badge--running";

  return (
    <div className={`pipeline-status-badge ${mod}`} role="status">
      {kind === "success" && <IconCheck />}
      {kind === "error" && <IconError />}
      {kind === "running" && (
        <span className="pipeline-status-badge-icon" aria-hidden>
          <span className="pipeline-status-spinner" />
        </span>
      )}
      <span className="pipeline-status-badge-label">{text}</span>
    </div>
  );
}
