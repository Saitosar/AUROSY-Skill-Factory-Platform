import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  createPackageFromJob,
  enqueueTrainJob,
  getJob,
  isSucceededJobStatus,
  isTerminalJobStatus,
  listJobs,
  platformJobId,
  savePlatformArtifact,
  type PlatformJobDetail,
  type PlatformJobSummary,
} from "../api/client";
import { TruncatedBlock } from "../components/PipelineOutput";
import { EmptyState } from "../components/ds/EmptyState";
import { PageHeader } from "../components/ds/PageHeader";
import { extractPipelineRefFromLocationState } from "../lib/jobsPipelineBridge";

const POLL_MS = 3500;

function formatTime(iso: string | undefined): string {
  if (!iso) return "—";
  const d = Date.parse(iso);
  if (Number.isNaN(d)) return iso;
  return new Date(d).toLocaleString();
}

export default function Jobs() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  if (jobId) {
    return <JobDetail jobId={jobId} onBack={() => navigate("/jobs")} />;
  }

  return <JobsHub />;
}

function JobDetail({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const { t } = useTranslation();
  const [job, setJob] = useState<PlatformJobDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [bundleBusy, setBundleBusy] = useState(false);
  const [bundleErr, setBundleErr] = useState<string | null>(null);
  const [createdPackageId, setCreatedPackageId] = useState<string | null>(null);

  useEffect(() => {
    setCreatedPackageId(null);
    setBundleErr(null);
  }, [jobId]);

  useEffect(() => {
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const tick = async () => {
      try {
        const j = await getJob(jobId);
        if (cancelled) return;
        setJob(j);
        setErr(null);
        setLoading(false);
        const st = typeof j.status === "string" ? j.status : "";
        if (isTerminalJobStatus(st) && intervalId !== undefined) {
          clearInterval(intervalId);
          intervalId = undefined;
        }
      } catch (e) {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
        setLoading(false);
      }
    };

    void tick();
    intervalId = setInterval(() => void tick(), POLL_MS);

    return () => {
      cancelled = true;
      if (intervalId !== undefined) clearInterval(intervalId);
    };
  }, [jobId]);

  const stdout = job && typeof job.stdout_tail === "string" ? job.stdout_tail : "";
  const stderr = job && typeof job.stderr_tail === "string" ? job.stderr_tail : "";
  const status = job && typeof job.status === "string" ? job.status : "—";
  const exitCode =
    job && "exit_code" in job && (typeof job.exit_code === "number" || job.exit_code === null)
      ? job.exit_code
      : undefined;

  async function onCreateBundle() {
    setBundleErr(null);
    setBundleBusy(true);
    try {
      const { package_id } = await createPackageFromJob(jobId);
      setCreatedPackageId(package_id);
      toast.success(t("jobs.bundleCreated", { id: package_id }));
    } catch (e) {
      const m = e instanceof Error ? e.message : String(e);
      setBundleErr(m);
      toast.error(t("jobs.bundleError"));
    } finally {
      setBundleBusy(false);
    }
  }

  const jobSucceeded = job
    ? isSucceededJobStatus(typeof job.status === "string" ? job.status : undefined)
    : false;

  return (
    <div className="jobs-page">
      <PageHeader
        title={t("jobs.detailTitle", { id: jobId })}
        description={t("jobs.detailLead")}
        action={
          <button type="button" className="secondary jobs-back" onClick={onBack}>
            {t("jobs.backToList")}
          </button>
        }
      />

      {loading && !job ? (
        <p className="muted">{t("jobs.loadingJob")}</p>
      ) : err && !job ? (
        <p className="warn-banner" role="alert">
          {err}
        </p>
      ) : null}

      {job ? (
        <div className="panel jobs-detail-panel">
          <dl className="jobs-detail-dl">
            <dt>{t("jobs.colStatus")}</dt>
            <dd>
              <code>{status}</code>
              {isTerminalJobStatus(typeof job.status === "string" ? job.status : undefined) ? null : (
                <span className="muted jobs-polling-hint"> {t("jobs.pollingHint")}</span>
              )}
            </dd>
            {exitCode !== undefined && exitCode !== null ? (
              <>
                <dt>exit_code</dt>
                <dd>
                  <code>{exitCode}</code>
                </dd>
              </>
            ) : null}
          </dl>
          {err ? (
            <p className="warn-banner" role="status">
              {t("jobs.refreshError", { error: err })}
            </p>
          ) : null}
          {stdout ? <TruncatedBlock title={t("jobs.stdoutTail")} value={stdout} /> : null}
          {stderr ? <TruncatedBlock title={t("jobs.stderrTail")} value={stderr} /> : null}
          {!stdout && !stderr && isTerminalJobStatus(typeof job.status === "string" ? job.status : undefined) ? (
            <p className="muted">{t("jobs.noLogsYet")}</p>
          ) : null}
          {jobSucceeded ? (
            <section className="jobs-bundle-section" aria-labelledby="jobs-bundle-heading">
              <h3 id="jobs-bundle-heading" className="jobs-section-title">
                {t("jobs.bundleSectionTitle")}
              </h3>
              <p className="muted jobs-section-lead">{t("jobs.bundleLead")}</p>
              <button
                type="button"
                className="primary"
                disabled={bundleBusy}
                aria-busy={bundleBusy}
                onClick={() => void onCreateBundle()}
              >
                {bundleBusy ? t("jobs.bundleBusy") : t("jobs.createBundle")}
              </button>
              {bundleErr ? (
                <p className="warn-banner" role="alert">
                  {bundleErr}
                </p>
              ) : null}
              {createdPackageId ? (
                <p className="muted jobs-bundle-result">
                  <code>{createdPackageId}</code> —{" "}
                  <Link to="/packages">{t("jobs.goToPackages")}</Link>
                </p>
              ) : null}
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

type RefMode = "inline" | "artifact";
type DemoMode = "none" | "inline" | "artifact";

function JobsHub() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<PlatformJobSummary[] | null>(null);
  const [jobsErr, setJobsErr] = useState<string | null>(null);
  const [jobsLoading, setJobsLoading] = useState(false);

  const [artifactName, setArtifactName] = useState("");
  const [artifactJson, setArtifactJson] = useState("{}");
  const [artifactBusy, setArtifactBusy] = useState(false);
  const [artifactFeedback, setArtifactFeedback] = useState<
    { kind: "ok" | "err"; text: string } | null
  >(null);

  const [refMode, setRefMode] = useState<RefMode>("inline");
  const [refArtifact, setRefArtifact] = useState("");
  const [refInline, setRefInline] = useState("{}");
  const [demoMode, setDemoMode] = useState<DemoMode>("none");
  const [demoArtifact, setDemoArtifact] = useState("");
  const [demoInline, setDemoInline] = useState("{}");
  const [trainMode, setTrainMode] = useState<"smoke" | "train">("smoke");
  const [trainBusy, setTrainBusy] = useState(false);
  const [trainErr, setTrainErr] = useState<string | null>(null);
  const [trainOk, setTrainOk] = useState<string | null>(null);
  const [pipelinePrefillBanner, setPipelinePrefillBanner] = useState(false);

  useEffect(() => {
    const payload = extractPipelineRefFromLocationState(location.state);
    if (payload === null) return;
    setRefMode("inline");
    setRefInline(JSON.stringify(payload, null, 2));
    setPipelinePrefillBanner(true);
    navigate("/jobs", { replace: true, state: {} });
  }, [location.state, navigate]);

  const loadJobs = useCallback(async () => {
    setJobsLoading(true);
    setJobsErr(null);
    try {
      const list = await listJobs();
      setJobs(list);
    } catch (e) {
      setJobsErr(e instanceof Error ? e.message : String(e));
      setJobs([]);
      toast.error(t("toast.networkError"));
    } finally {
      setJobsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const clientTrainError = useMemo(() => {
    const hasRefArt = refMode === "artifact" && refArtifact.trim().length > 0;
    const hasRefIn = refMode === "inline" && refInline.trim().length > 0;
    if (hasRefArt && hasRefIn) return t("jobs.errRefBoth");
    if (!hasRefArt && !hasRefIn) return t("jobs.errRefNone");

    const hasDemoArt = demoMode === "artifact" && demoArtifact.trim().length > 0;
    const hasDemoIn = demoMode === "inline" && demoInline.trim().length > 0;
    if (hasDemoArt && hasDemoIn) return t("jobs.errDemoBoth");
    return null;
  }, [demoArtifact, demoInline, demoMode, refArtifact, refInline, refMode, t]);

  async function onSaveArtifact(e: FormEvent) {
    e.preventDefault();
    setArtifactFeedback(null);
    const name = artifactName.trim();
    if (!name) {
      setArtifactFeedback({ kind: "err", text: t("jobs.errArtifactName") });
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(artifactJson) as unknown;
    } catch {
      setArtifactFeedback({ kind: "err", text: t("jobs.errArtifactJson") });
      return;
    }
    setArtifactBusy(true);
    try {
      await savePlatformArtifact(name, parsed);
      setArtifactFeedback({ kind: "ok", text: t("jobs.artifactSaved") });
      toast.success(t("jobs.artifactSaved"));
    } catch (err) {
      const m = err instanceof Error ? err.message : String(err);
      setArtifactFeedback({ kind: "err", text: m });
      toast.error(t("toast.networkError"));
    } finally {
      setArtifactBusy(false);
    }
  }

  async function onEnqueueTrain(e: FormEvent) {
    e.preventDefault();
    setTrainErr(null);
    setTrainOk(null);
    if (clientTrainError) {
      setTrainErr(clientTrainError);
      return;
    }

    let body: Parameters<typeof enqueueTrainJob>[0] = { mode: trainMode };

    if (refMode === "artifact") {
      body = { ...body, reference_artifact: refArtifact.trim() };
    } else {
      try {
        body = { ...body, reference_trajectory: JSON.parse(refInline) as unknown };
      } catch {
        setTrainErr(t("jobs.errRefJson"));
        return;
      }
    }

    if (demoMode === "artifact") {
      body = { ...body, demonstration_artifact: demoArtifact.trim() };
    } else if (demoMode === "inline") {
      try {
        body = { ...body, demonstration_dataset: JSON.parse(demoInline) as unknown };
      } catch {
        setTrainErr(t("jobs.errDemoJson"));
        return;
      }
    }

    setTrainBusy(true);
    try {
      const { job_id } = await enqueueTrainJob(body);
      setTrainOk(t("jobs.trainEnqueued", { id: job_id }));
      toast.success(t("jobs.trainEnqueued", { id: job_id }));
      void loadJobs();
    } catch (err) {
      const m = err instanceof Error ? err.message : String(err);
      setTrainErr(m);
      toast.error(t("toast.networkError"));
    } finally {
      setTrainBusy(false);
    }
  }

  return (
    <div className="jobs-page">
      <PageHeader
        title={t("jobs.title")}
        description={
          <Trans
            i18nKey="jobs.lead"
            components={{
              strong: <strong />,
              c1: <code />,
              c2: <code />,
            }}
          />
        }
      />

      <p className="warn-banner jobs-worker-hint" role="note">
        <Trans i18nKey="jobs.workerHint" components={{ c1: <code /> }} />
      </p>

      {pipelinePrefillBanner ? (
        <div className="jobs-pipeline-prefill-banner" role="status">
          <p className="jobs-pipeline-prefill-text">{t("jobs.prefilledFromPipeline")}</p>
          <button type="button" className="secondary jobs-pipeline-prefill-dismiss" onClick={() => setPipelinePrefillBanner(false)}>
            {t("jobs.prefilledFromPipelineDismiss")}
          </button>
        </div>
      ) : null}

      <section className="panel jobs-section" aria-labelledby="jobs-artifact-heading">
        <h2 id="jobs-artifact-heading" className="jobs-section-title">
          {t("jobs.sectionArtifact")}
        </h2>
        <p className="muted jobs-section-lead">{t("jobs.sectionArtifactLead")}</p>
        <form onSubmit={onSaveArtifact} className="jobs-form">
          <label className="jobs-label">
            {t("jobs.artifactName")}
            <input
              type="text"
              className="jobs-input"
              value={artifactName}
              onChange={(e) => setArtifactName(e.target.value)}
              placeholder={t("jobs.artifactNamePh")}
              autoComplete="off"
            />
          </label>
          <label className="jobs-label">
            {t("jobs.artifactJson")}
            <textarea
              className="jobs-textarea"
              rows={8}
              value={artifactJson}
              onChange={(e) => setArtifactJson(e.target.value)}
              spellCheck={false}
            />
          </label>
          <button type="submit" className="primary" disabled={artifactBusy} aria-busy={artifactBusy}>
            {t("jobs.saveArtifact")}
          </button>
          {artifactFeedback ? (
            <p
              className={artifactFeedback.kind === "ok" ? "muted" : "warn-banner"}
              role="status"
            >
              {artifactFeedback.text}
            </p>
          ) : null}
        </form>
      </section>

      <section className="panel jobs-section" aria-labelledby="jobs-train-heading">
        <h2 id="jobs-train-heading" className="jobs-section-title">
          {t("jobs.sectionTrain")}
        </h2>
        <p className="muted jobs-section-lead">{t("jobs.sectionTrainLead")}</p>
        <form onSubmit={onEnqueueTrain} className="jobs-form">
          <fieldset className="jobs-fieldset">
            <legend>{t("jobs.refSource")}</legend>
            <label className="jobs-radio">
              <input
                type="radio"
                name="refMode"
                checked={refMode === "inline"}
                onChange={() => setRefMode("inline")}
              />
              {t("jobs.refInline")}
            </label>
            <label className="jobs-radio">
              <input
                type="radio"
                name="refMode"
                checked={refMode === "artifact"}
                onChange={() => setRefMode("artifact")}
              />
              {t("jobs.refArtifact")}
            </label>
          </fieldset>
          {refMode === "inline" ? (
            <label className="jobs-label">
              {t("jobs.refInlineJson")}
              <textarea
                className="jobs-textarea"
                rows={6}
                value={refInline}
                onChange={(e) => setRefInline(e.target.value)}
                spellCheck={false}
              />
            </label>
          ) : (
            <label className="jobs-label">
              {t("jobs.refArtifactName")}
              <input
                type="text"
                className="jobs-input"
                value={refArtifact}
                onChange={(e) => setRefArtifact(e.target.value)}
                autoComplete="off"
              />
            </label>
          )}

          <fieldset className="jobs-fieldset">
            <legend>{t("jobs.demoSource")}</legend>
            <label className="jobs-radio">
              <input
                type="radio"
                name="demoMode"
                checked={demoMode === "none"}
                onChange={() => setDemoMode("none")}
              />
              {t("jobs.demoNone")}
            </label>
            <label className="jobs-radio">
              <input
                type="radio"
                name="demoMode"
                checked={demoMode === "inline"}
                onChange={() => setDemoMode("inline")}
              />
              {t("jobs.demoInline")}
            </label>
            <label className="jobs-radio">
              <input
                type="radio"
                name="demoMode"
                checked={demoMode === "artifact"}
                onChange={() => setDemoMode("artifact")}
              />
              {t("jobs.demoArtifact")}
            </label>
          </fieldset>
          {demoMode === "inline" ? (
            <label className="jobs-label">
              {t("jobs.demoInlineJson")}
              <textarea
                className="jobs-textarea"
                rows={5}
                value={demoInline}
                onChange={(e) => setDemoInline(e.target.value)}
                spellCheck={false}
              />
            </label>
          ) : null}
          {demoMode === "artifact" ? (
            <label className="jobs-label">
              {t("jobs.demoArtifactName")}
              <input
                type="text"
                className="jobs-input"
                value={demoArtifact}
                onChange={(e) => setDemoArtifact(e.target.value)}
                autoComplete="off"
              />
            </label>
          ) : null}

          <label className="jobs-label">
            {t("jobs.trainMode")}
            <select
              className="jobs-input"
              value={trainMode}
              onChange={(e) => setTrainMode(e.target.value as "smoke" | "train")}
            >
              <option value="smoke">smoke</option>
              <option value="train">train</option>
            </select>
          </label>

          {clientTrainError ? (
            <p className="warn-banner" role="alert">
              {clientTrainError}
            </p>
          ) : null}
          <button type="submit" className="primary" disabled={trainBusy} aria-busy={trainBusy}>
            {t("jobs.enqueueTrain")}
          </button>
          {trainErr ? (
            <p className="warn-banner" role="alert">
              {trainErr}
            </p>
          ) : null}
          {trainOk ? (
            <p className="muted" role="status">
              {trainOk}
            </p>
          ) : null}
        </form>
      </section>

      <section className="panel jobs-section" aria-labelledby="jobs-list-heading">
        <div className="jobs-list-header">
          <h2 id="jobs-list-heading" className="jobs-section-title">
            {t("jobs.sectionList")}
          </h2>
          <button type="button" className="secondary" onClick={() => void loadJobs()} disabled={jobsLoading}>
            {t("jobs.refreshList")}
          </button>
        </div>
        {jobsLoading && !jobs?.length ? (
          <p className="muted">{t("jobs.loadingList")}</p>
        ) : jobsErr ? (
          <p className="warn-banner">{jobsErr}</p>
        ) : null}
        {!jobsLoading && jobs && jobs.length === 0 ? (
          <EmptyState title={t("jobs.emptyListTitle")} description={t("jobs.emptyListDesc")} />
        ) : null}
        {jobs && jobs.length > 0 ? (
          <div className="table-wrap">
            <table className="data jobs-table">
              <thead>
                <tr>
                  <th scope="col">{t("jobs.colId")}</th>
                  <th scope="col">{t("jobs.colStatus")}</th>
                  <th scope="col">{t("jobs.colCreated")}</th>
                  <th scope="col">{t("jobs.colAction")}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((row) => {
                  const id = platformJobId(row);
                  const st = typeof row.status === "string" ? row.status : "—";
                  const created = formatTime(
                    typeof row.created_at === "string" ? row.created_at : undefined
                  );
                  return (
                    <tr key={id || JSON.stringify(row)}>
                      <td>
                        <code>{id || "—"}</code>
                      </td>
                      <td>
                        <code>{st}</code>
                      </td>
                      <td className="muted">{created}</td>
                      <td>
                        {id ? (
                          <Link to={`/jobs/${encodeURIComponent(id)}`} className="jobs-detail-link">
                            {t("jobs.openDetail")}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
