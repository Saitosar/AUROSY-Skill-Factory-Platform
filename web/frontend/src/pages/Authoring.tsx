import { Trans, useTranslation } from "react-i18next";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { validateApi } from "../api/client";
import { PageHeader } from "../components/ds/PageHeader";
import { ValidateBanner } from "../components/ds/ValidateBanner";
import i18n from "../i18n/config";
import { extractKeyframesPrefillFromLocationState } from "../lib/poseAuthoringBridge";
import {
  getExpectedAuthoringSchemaVersion,
  validateAgainstSchema,
} from "../lib/schemaValidate";

const DEFAULT_KEYFRAMES = `{
  "schema_version": "1.0.0",
  "robot_model": "g1_29dof",
  "units": { "angle": "degrees", "time": "seconds" },
  "keyframes": [
    { "timestamp_s": 0.0, "joints_deg": { "0": 0.0, "1": 1.0, "2": -1.0 } },
    { "timestamp_s": 0.5, "joints_deg": { "0": 2.0, "1": 2.0, "2": -2.0 } }
  ]
}`;

const DEFAULT_MOTION = `{
  "schema_version": "1.0.0",
  "motion_id": "lezginka_kf_demo_v1",
  "source_keyframes_id": "lezginka_kf_source_v1",
  "keyframe_timestamps_s": [0.0, 0.5],
  "metadata": { "name": "Golden motion for phase0" }
}`;

const DEFAULT_SCENARIO = `{
  "schema_version": "1.0.0",
  "scenario_id": "lezginka_scenario_v1",
  "steps": [
    {
      "motion_id": "lezginka_kf_demo_v1",
      "transition": { "type": "on_complete" }
    }
  ]
}`;

type Tab = "keyframes" | "motion" | "scenario";

function fixturePathForTab(t: Tab): string {
  if (t === "keyframes") return "/fixtures/golden/v1/keyframes.json";
  if (t === "motion") return "/fixtures/golden/v1/motion.json";
  return "/fixtures/golden/v1/scenario.json";
}

export default function Authoring() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("keyframes");
  const [kf, setKf] = useState(DEFAULT_KEYFRAMES);
  const [motion, setMotion] = useState(DEFAULT_MOTION);
  const [scenario, setScenario] = useState(DEFAULT_SCENARIO);
  const [clientErr, setClientErr] = useState<string[] | null>(null);
  const [serverErr, setServerErr] = useState<string[] | null>(null);
  const [serverOk, setServerOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [expectedSchemaVersion, setExpectedSchemaVersion] = useState<string | null>(null);
  const [goldenLoadErr, setGoldenLoadErr] = useState<string | null>(null);
  const [selectedClientErrIndex, setSelectedClientErrIndex] = useState<number | null>(null);

  const text = tab === "keyframes" ? kf : tab === "motion" ? motion : scenario;
  const setText =
    tab === "keyframes" ? setKf : tab === "motion" ? setMotion : setScenario;

  const schemaPath = useMemo(() => {
    if (tab === "keyframes") return "/contracts/authoring/keyframes.schema.json" as const;
    if (tab === "motion") return "/contracts/authoring/motion.schema.json" as const;
    return "/contracts/authoring/scenario.schema.json" as const;
  }, [tab]);

  const kind = useMemo(() => {
    if (tab === "keyframes") return "keyframes" as const;
    if (tab === "motion") return "motion" as const;
    return "scenario" as const;
  }, [tab]);

  useEffect(() => {
    setClientErr(null);
    setServerErr(null);
    setServerOk(false);
    setGoldenLoadErr(null);
    setSelectedClientErrIndex(null);
  }, [tab]);

  useEffect(() => {
    setSelectedClientErrIndex(null);
  }, [clientErr]);

  useEffect(() => {
    let cancelled = false;
    void getExpectedAuthoringSchemaVersion(schemaPath).then((v) => {
      if (!cancelled) setExpectedSchemaVersion(v);
    });
    return () => {
      cancelled = true;
    };
  }, [schemaPath]);

  useEffect(() => {
    const pre = extractKeyframesPrefillFromLocationState(location.state);
    if (!pre) return;
    try {
      const parsed = JSON.parse(pre) as unknown;
      const pretty = `${JSON.stringify(parsed, null, 2)}\n`;
      setKf(pretty.trimEnd());
      setTab("keyframes");
      toast.success(t("authoring.prefillFromPoseOk"));
    } catch (e) {
      toast.error(t("authoring.prefillFromPoseErr"), {
        description: e instanceof Error ? e.message : String(e),
      });
    }
    navigate(location.pathname, { replace: true, state: {} });
  }, [location.state, location.pathname, navigate, t]);

  const payloadSchemaVersion = useMemo(() => {
    try {
      const o = JSON.parse(text) as Record<string, unknown>;
      const v = o.schema_version;
      return typeof v === "string" ? v : null;
    } catch {
      return null;
    }
  }, [text]);

  const versionMismatch =
    expectedSchemaVersion != null &&
    payloadSchemaVersion != null &&
    payloadSchemaVersion !== expectedSchemaVersion;

  async function loadGoldenFixture() {
    setGoldenLoadErr(null);
    const path = fixturePathForTab(tab);
    try {
      const r = await fetch(path);
      if (!r.ok) {
        setGoldenLoadErr(t("authoring.goldenLoadFailed", { path, status: r.status }));
        return;
      }
      const raw = await r.text();
      JSON.parse(raw);
      setText(raw);
    } catch (e) {
      setGoldenLoadErr(e instanceof Error ? e.message : String(e));
    }
  }

  function formatJson() {
    try {
      const parsed = JSON.parse(text) as unknown;
      const pretty = `${JSON.stringify(parsed, null, 2)}\n`;
      setText(pretty.trimEnd());
    } catch (e) {
      toast.error(t("authoring.formatInvalid"), {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  }

  async function copyJson() {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("authoring.copied"));
    } catch (e) {
      toast.error(t("authoring.copyFailed"), {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  }

  async function validateClient() {
    setClientErr(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setClientErr([`JSON: ${e instanceof Error ? e.message : String(e)}`]);
      return;
    }
    const r = await validateAgainstSchema(schemaPath, parsed);
    if (!r.ok) setClientErr(r.errors);
  }

  async function validateServer() {
    setServerErr(null);
    setServerOk(false);
    setBusy(true);
    try {
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch (e) {
        setServerErr([`JSON: ${e instanceof Error ? e.message : String(e)}`]);
        return;
      }
      const r = await validateApi(kind, parsed);
      if (r.ok) setServerOk(true);
      else setServerErr(r.errors);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setServerErr([msg]);
      toast.error(i18n.t("toast.networkError"), { description: msg });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title={t("authoring.title")}
        description={
          <Trans
            i18nKey="authoring.lead"
            components={{ c1: <code>skill_foundry_phase0</code> }}
          />
        }
      />
      {versionMismatch && (
        <ValidateBanner variant="warning">
          <Trans
            i18nKey="authoring.versionMismatch"
            values={{ payload: payloadSchemaVersion, expected: expectedSchemaVersion }}
            components={{ c1: <code>schema_version</code> }}
          />
        </ValidateBanner>
      )}
      <div className="authoring-tabs-row">
        <div className="tabs" role="tablist" aria-label={t("authoring.tabsAria")}>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "keyframes"}
            className={tab === "keyframes" ? "active" : ""}
            onClick={() => setTab("keyframes")}
          >
            keyframes.json
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "motion"}
            className={tab === "motion" ? "active" : ""}
            onClick={() => setTab("motion")}
          >
            motion.json
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "scenario"}
            className={tab === "scenario" ? "active" : ""}
            onClick={() => setTab("scenario")}
          >
            scenario.json
          </button>
        </div>
        <div className="authoring-schema-badges muted" aria-label={t("authoring.schemaBadgesAria")}>
          <span>
            {t("authoring.badgeSchema", { kind })}{" "}
            {expectedSchemaVersion != null ? (
              <code>{expectedSchemaVersion}</code>
            ) : (
              <span>{t("common.dash")}</span>
            )}
          </span>
          <span>
            <Trans i18nKey="authoring.badgeDocument" components={{ c1: <code /> }} />{" "}
            {payloadSchemaVersion != null ? (
              <code>{payloadSchemaVersion}</code>
            ) : (
              <span>{t("common.dash")}</span>
            )}
          </span>
        </div>
      </div>
      <div className="panel">
        <div className="row" style={{ marginBottom: 10, flexWrap: "wrap" }}>
          <button type="button" className="secondary" onClick={() => void validateClient()}>
            {t("authoring.validateClient")}
          </button>
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => void validateServer()}
          >
            {t("authoring.validateServer")}
          </button>
          <button type="button" className="secondary" onClick={() => void loadGoldenFixture()}>
            {t("authoring.loadGolden")}
          </button>
          <button type="button" className="secondary" onClick={() => formatJson()}>
            {t("authoring.formatJson")}
          </button>
          <button type="button" className="secondary" onClick={() => void copyJson()}>
            {t("authoring.copyJson")}
          </button>
        </div>
        {goldenLoadErr && (
          <p className="err" style={{ marginTop: 0 }}>
            {goldenLoadErr}
          </p>
        )}
        {clientErr && clientErr.length > 0 && (
          <ValidateBanner
            variant="error"
            title={t("common.schemaClientTitle")}
            errors={clientErr}
            selectable
            selectedErrorIndex={selectedClientErrIndex}
            onSelectError={setSelectedClientErrIndex}
            copyPathAriaLabel={t("authoring.copyPathAria")}
          />
        )}
        {serverErr && serverErr.length > 0 && (
          <ValidateBanner variant="error" title={t("common.serverPhase0Title")} errors={serverErr} />
        )}
        {serverOk && (
          <ValidateBanner variant="success">{t("common.serverPhase0Ok")}</ValidateBanner>
        )}
        <textarea
          className="code"
          spellCheck={false}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
    </div>
  );
}
