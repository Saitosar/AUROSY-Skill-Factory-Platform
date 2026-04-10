import { Trans, useTranslation } from "react-i18next";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  getCliDetection,
  getMeta,
  runPlayback,
  runPreprocess,
  runTrain,
  validateApi,
  type PipelineSubprocessJsonResult,
  type PreprocessPipelineResponse,
} from "../api/client";
import {
  ErrorWithExpand,
  PipelineSubprocessResultView,
  PreprocessResultView,
} from "../components/PipelineOutput";
import { PageHeader } from "../components/ds/PageHeader";
import { PipelineStatusBadge } from "../components/ds/PipelineStatusBadge";
import { ValidateBanner } from "../components/ds/ValidateBanner";
import { extractKeyframesPrefillFromLocationState } from "../lib/poseAuthoringBridge";
import { PIPELINE_REF_TRAJECTORY_STATE_KEY } from "../lib/jobsPipelineBridge";
import { preprocessExitOk, subprocessExitOk } from "../lib/pipelineStatus";
import i18n from "../i18n/config";

const SAMPLE_KEYFRAMES = `{
  "schema_version": "1.0.0",
  "robot_model": "g1_29dof",
  "units": { "angle": "degrees", "time": "seconds" },
  "keyframes": [
    { "timestamp_s": 0.0, "joints_deg": { "15": 0.0, "22": 0.0 } },
    { "timestamp_s": 0.4, "joints_deg": { "15": 20.0, "22": -10.0 } }
  ]
}`;

type Busy = "validate" | "preprocess" | "playback" | "train" | null;

type ResultOrErr<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

export default function Pipeline() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [meta, setMeta] = useState<{
    sdk_python_root: string;
    mjcf_default: string | null;
  } | null>(null);
  const [metaErr, setMetaErr] = useState<string | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);

  const [cli, setCli] = useState<Record<string, string | null> | null>(null);
  const [cliErr, setCliErr] = useState<string | null>(null);

  const [kfText, setKfText] = useState(SAMPLE_KEYFRAMES);
  const [freq, setFreq] = useState(50);

  const [validateErrors, setValidateErrors] = useState<string[] | null>(null);
  const [validateOk, setValidateOk] = useState(false);

  const [preView, setPreView] = useState<ResultOrErr<PreprocessPipelineResponse> | null>(null);
  const [pbView, setPbView] = useState<ResultOrErr<PipelineSubprocessJsonResult> | null>(null);
  const [trainView, setTrainView] = useState<ResultOrErr<PipelineSubprocessJsonResult> | null>(null);

  const [refPath, setRefPath] = useState("");
  const [trainCfgPath, setTrainCfgPath] = useState("");
  const [busy, setBusy] = useState<Busy>(null);

  const anyBusy = busy !== null;
  const validationFailed = validateErrors !== null && validateErrors.length > 0;

  const preprocessRefTransfer = useMemo(() => {
    if (!preView || !preView.ok || !preprocessExitOk(preView.data)) return null;
    const raw = preView.data.reference_trajectory_json;
    if (raw == null || !String(raw).trim()) return null;
    try {
      return { kind: "ready" as const, parsed: JSON.parse(raw) as unknown };
    } catch {
      return { kind: "badJson" as const };
    }
  }, [preView]);

  const cliMissingInPath =
    cli &&
    (cli.preprocess === null || cli.playback === null || cli.train === null);

  const dash = t("common.dash");

  useEffect(() => {
    setValidateErrors(null);
    setValidateOk(false);
  }, [kfText]);

  useEffect(() => {
    const pre = extractKeyframesPrefillFromLocationState(location.state);
    if (!pre) return;
    try {
      const parsed = JSON.parse(pre) as unknown;
      const pretty = `${JSON.stringify(parsed, null, 2)}\n`;
      setKfText(pretty.trimEnd());
      toast.success(t("pipeline.prefillKeyframesOk"));
    } catch (e) {
      toast.error(t("pipeline.prefillKeyframesErr"), {
        description: e instanceof Error ? e.message : String(e),
      });
    }
    navigate(location.pathname, { replace: true, state: {} });
  }, [location.state, location.pathname, navigate, t]);

  useEffect(() => {
    setMetaLoading(true);
    void getMeta()
      .then((m) => {
        setMeta({ sdk_python_root: m.sdk_python_root, mjcf_default: m.mjcf_default });
        setMetaErr(null);
      })
      .catch((e: unknown) => {
        setMeta(null);
        setMetaErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setMetaLoading(false));

    void getCliDetection()
      .then((c) => {
        setCli(c.commands);
        setCliErr(null);
      })
      .catch((e: unknown) => {
        setCli(null);
        setCliErr(e instanceof Error ? e.message : String(e));
      });
  }, []);

  function parseKeyframes(): object {
    return JSON.parse(kfText) as object;
  }

  async function runValidate() {
    setValidateErrors(null);
    setValidateOk(false);
    setBusy("validate");
    try {
      let payload: unknown;
      try {
        payload = parseKeyframes();
      } catch (e) {
        setValidateErrors([`JSON: ${e instanceof Error ? e.message : String(e)}`]);
        return;
      }
      const r = await validateApi("keyframes", payload);
      if (r.ok) {
        setValidateOk(true);
      } else {
        setValidateErrors(r.errors);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setValidateErrors([msg]);
      toast.error(i18n.t("toast.networkError"), { description: msg });
    } finally {
      setBusy(null);
    }
  }

  async function preprocess() {
    setPreView(null);
    setBusy("preprocess");
    try {
      const data = parseKeyframes();
      const r = await runPreprocess(data, freq);
      setPreView({ ok: true, data: r });
    } catch (e) {
      setPreView({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  async function playback() {
    setPbView(null);
    setBusy("playback");
    try {
      const body: Parameters<typeof runPlayback>[0] = {
        mjcf_path: meta?.mjcf_default ?? undefined,
        mode: "dynamic",
        write_demonstration_json: false,
        max_steps: 200,
      };
      if (refPath.trim()) {
        body.reference_path = refPath.trim();
      } else {
        const pre = parseKeyframes();
        const prep = await runPreprocess(pre, freq);
        if (!prep.reference_trajectory_json) {
          setPbView({ ok: false, error: t("pipeline.errNoRefJson") });
          return;
        }
        body.reference_trajectory = JSON.parse(prep.reference_trajectory_json) as object;
      }
      const r = await runPlayback(body);
      setPbView({ ok: true, data: r });
    } catch (e) {
      setPbView({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  async function train() {
    setTrainView(null);
    if (!refPath.trim() && !trainCfgPath.trim()) {
      setTrainView({
        ok: false,
        error: t("pipeline.errTrainPaths"),
      });
      return;
    }
    setBusy("train");
    try {
      const r = await runTrain({
        mode: "smoke",
        reference_path: refPath.trim(),
        config_path: trainCfgPath.trim() || undefined,
      });
      setTrainView({ ok: true, data: r });
    } catch (e) {
      setTrainView({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <PageHeader
        title={t("pipeline.title")}
        description={
          <Trans
            i18nKey="pipeline.lead"
            components={{
              c1: <code>skill-foundry-preprocess</code>,
              c2: <code>skill-foundry-playback</code>,
              c3: <code>skill-foundry-train</code>,
              link: <Link to="/authoring" />,
            }}
          />
        }
      />

      {cliMissingInPath && (
        <ValidateBanner variant="warning">
          <Trans
            i18nKey="pipeline.cliWarn"
            components={{
              c1: <code>PATH</code>,
              c2: <code>python -m …</code>,
            }}
          />
        </ValidateBanner>
      )}

      {!metaLoading && metaErr && (
        <p className="muted err" role="status">
          <Trans
            i18nKey="pipeline.metaLoadErr"
            values={{ error: metaErr }}
            components={{ c1: <code>/api/meta</code> }}
          />
        </p>
      )}
      {meta && (
        <p className="muted">
          {t("pipeline.sdkLabel")} <code>{meta.sdk_python_root}</code>
          <br />
          {t("pipeline.mjcfDefault")}{" "}
          {meta.mjcf_default ? <code>{meta.mjcf_default}</code> : t("pipeline.mjcfNotFound")}
        </p>
      )}

      {cliErr && (
        <p className="muted err" role="status">
          <Trans
            i18nKey="pipeline.cliDetectErr"
            values={{ error: cliErr }}
            components={{ c1: <code>/api/pipeline/detect-cli</code> }}
          />
        </p>
      )}
      {cli && !cliErr && (
        <p className="muted">
          <Trans
            i18nKey="pipeline.cliInPath"
            values={{
              pre: cli.preprocess ?? dash,
              pb: cli.playback ?? dash,
              tr: cli.train ?? dash,
            }}
            components={{ c1: <code>python -m …</code> }}
          />
        </p>
      )}

      <div className="panel pipeline-ia-panel" role="region" aria-label={t("pipeline.iaRegionAria")}>
        <p className="muted pipeline-ia-panel-text" style={{ marginTop: 0 }}>
          <Trans
            i18nKey="pipeline.trainPathsInfo"
            components={{
              strong: <strong />,
              c1: <code>POST /api/pipeline/train</code>,
              c2: <code>POST /api/jobs/train</code>,
              lj: <Link to="/jobs" />,
            }}
          />
        </p>
      </div>

      <div className="panel pipeline-platform-handoff" role="note">
        <p className="muted" style={{ margin: 0 }}>
          <Trans
            i18nKey="pipeline.actionReadyHandoff"
            components={{
              c1: <code />,
              lh: <Link to="/help#faq-skillfactory-heading" />,
            }}
          />
        </p>
      </div>

      <div className="pipeline-flow" role="navigation" aria-label={t("pipeline.flowAria")}>
        <div className="pipeline-flow-step">
          <strong>{t("pipeline.flowStep1")}</strong>
          <div className="muted" style={{ fontSize: "0.78rem", marginTop: 4 }}>
            {t("pipeline.flowStep1Hint")}
          </div>
        </div>
        <span className="pipeline-flow-arrow" aria-hidden>
          →
        </span>
        <div className="pipeline-flow-step">
          <strong>{t("pipeline.flowStep2")}</strong>
          <div className="muted" style={{ fontSize: "0.78rem", marginTop: 4 }}>
            {t("pipeline.flowStep2Hint")}
          </div>
        </div>
        <span className="pipeline-flow-arrow" aria-hidden>
          →
        </span>
        <div className="pipeline-flow-step">
          <strong>{t("pipeline.flowStep3")}</strong>
          <div className="muted" style={{ fontSize: "0.78rem", marginTop: 4 }}>
            {t("pipeline.flowStep3Hint")}
          </div>
        </div>
        <span className="pipeline-flow-arrow" aria-hidden>
          →
        </span>
        <div className="pipeline-flow-step pipeline-flow-step-optional">
          <strong>{t("pipeline.flowStep4")}</strong>
          <div className="muted" style={{ fontSize: "0.78rem", marginTop: 4 }}>
            {t("pipeline.flowStep4Hint")}
          </div>
        </div>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{t("pipeline.phase0Title")}</h3>
        <p className="muted">{t("pipeline.phase0Lead")}</p>
        <div className="row" style={{ marginBottom: 10 }}>
          <button
            type="button"
            className="primary"
            disabled={anyBusy}
            aria-busy={busy === "validate"}
            onClick={() => void runValidate()}
          >
            {t("pipeline.validateServer")}
          </button>
        </div>
        {validateErrors && validateErrors.length > 0 && (
          <ValidateBanner variant="error" title={t("common.serverPhase0Title")} errors={validateErrors} />
        )}
        {validateOk && <ValidateBanner variant="success">{t("common.serverPhase0Ok")}</ValidateBanner>}
      </div>

      {validationFailed && (
        <ValidateBanner variant="warning">{t("pipeline.validateWarn")}</ValidateBanner>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{t("pipeline.preprocessTitle")}</h3>
        <label className="muted">
          frequency_hz{" "}
          <input
            type="number"
            value={freq}
            onChange={(e) => setFreq(Number(e.target.value))}
          />
        </label>
        <textarea className="code" value={kfText} onChange={(e) => setKfText(e.target.value)} spellCheck={false} />
        <div className="row" style={{ marginTop: 8 }}>
          <button
            type="button"
            className="primary"
            disabled={anyBusy}
            aria-busy={busy === "preprocess"}
            onClick={() => void preprocess()}
          >
            {t("pipeline.runPreprocess")}
          </button>
        </div>
        {busy === "preprocess" && (
          <div aria-live="polite" aria-atomic="true">
            <PipelineStatusBadge kind="running" />
          </div>
        )}
        {preView && preView.ok && (
          <>
            {preprocessExitOk(preView.data) ? (
              <PipelineStatusBadge kind="success" />
            ) : (
              <PipelineStatusBadge kind="error" />
            )}
            <PreprocessResultView result={preView.data} />
            {preprocessRefTransfer?.kind === "ready" ? (
              <div className="panel pipeline-preprocess-cta" role="region" aria-label={t("pipeline.preprocessCtaTitle")}>
                <h4 className="pipeline-preprocess-cta-title">{t("pipeline.preprocessCtaTitle")}</h4>
                <p className="muted pipeline-preprocess-cta-lead">
                  <Trans i18nKey="pipeline.preprocessCtaLead" components={{ c1: <code>reference_trajectory</code> }} />
                </p>
                <div className="row pipeline-preprocess-cta-actions">
                  <button
                    type="button"
                    className="primary"
                    disabled={anyBusy}
                    onClick={() =>
                      navigate("/jobs", {
                        state: { [PIPELINE_REF_TRAJECTORY_STATE_KEY]: preprocessRefTransfer.parsed },
                      })
                    }
                  >
                    {t("pipeline.preprocessCtaButton")}
                  </button>
                  <Link className="pipeline-preprocess-cta-help" to="/help">
                    {t("pipeline.preprocessCtaHelp")}
                  </Link>
                </div>
              </div>
            ) : null}
            {preprocessRefTransfer?.kind === "badJson" ? (
              <p className="warn-banner" role="alert">
                {t("pipeline.preprocessRefParseErr")}
              </p>
            ) : null}
          </>
        )}
        {preView && !preView.ok && (
          <>
            <PipelineStatusBadge kind="error" />
            <ErrorWithExpand message={preView.error} />
          </>
        )}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{t("pipeline.playbackTitle")}</h3>
        <p className="muted">
          <Trans
            i18nKey="pipeline.playbackLead"
            components={{ c1: <code>max_steps=200</code> }}
          />
        </p>
        <label className="muted">
          {t("pipeline.refPathLabel")}{" "}
          <input
            type="text"
            style={{ width: "100%", maxWidth: 560 }}
            value={refPath}
            onChange={(e) => setRefPath(e.target.value)}
            placeholder="/abs/path/to/reference_trajectory.json"
          />
        </label>
        <div className="row" style={{ marginTop: 8 }}>
          <button
            type="button"
            className="primary"
            disabled={anyBusy}
            aria-busy={busy === "playback"}
            onClick={() => void playback()}
          >
            {t("pipeline.runPlayback")}
          </button>
        </div>
        {busy === "playback" && (
          <div aria-live="polite" aria-atomic="true">
            <PipelineStatusBadge kind="running" />
          </div>
        )}
        {pbView && pbView.ok && (
          <>
            {subprocessExitOk(pbView.data) ? (
              <PipelineStatusBadge kind="success" />
            ) : (
              <PipelineStatusBadge kind="error" />
            )}
            <PipelineSubprocessResultView result={pbView.data} />
          </>
        )}
        {pbView && !pbView.ok && (
          <>
            <PipelineStatusBadge kind="error" />
            <ErrorWithExpand message={pbView.error} />
          </>
        )}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{t("pipeline.trainTitle")}</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          <Trans
            i18nKey="pipeline.trainSyncLead"
            components={{
              c1: <code>POST /api/pipeline/train</code>,
              lj: <Link to="/jobs" />,
            }}
          />
        </p>
        <label className="muted">
          {t("pipeline.trainRefLabel")}{" "}
          <input
            type="text"
            style={{ width: "100%", maxWidth: 560 }}
            value={refPath}
            onChange={(e) => setRefPath(e.target.value)}
          />
        </label>
        <label className="muted" style={{ display: "block", marginTop: 8 }}>
          {t("pipeline.trainConfigLabel")}{" "}
          <input
            type="text"
            style={{ width: "100%", maxWidth: 560 }}
            value={trainCfgPath}
            onChange={(e) => setTrainCfgPath(e.target.value)}
          />
        </label>
        <div className="row" style={{ marginTop: 8 }}>
          <button
            type="button"
            className="primary"
            disabled={anyBusy}
            aria-busy={busy === "train"}
            onClick={() => void train()}
          >
            {t("pipeline.runTrain")}
          </button>
        </div>
        {busy === "train" && (
          <div aria-live="polite" aria-atomic="true">
            <PipelineStatusBadge kind="running" />
          </div>
        )}
        {trainView && trainView.ok && (
          <>
            {subprocessExitOk(trainView.data) ? (
              <PipelineStatusBadge kind="success" />
            ) : (
              <PipelineStatusBadge kind="error" />
            )}
            <PipelineSubprocessResultView result={trainView.data} />
          </>
        )}
        {trainView && !trainView.ok && (
          <>
            <PipelineStatusBadge kind="error" />
            <ErrorWithExpand message={trainView.error} />
          </>
        )}
      </div>
    </div>
  );
}
