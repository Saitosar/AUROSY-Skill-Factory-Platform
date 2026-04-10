import { Trans, useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { getConfiguredApiBase, getMeta } from "../api/client";
import { LOCAL_BACKEND_START, LOCAL_SIMULATOR_START } from "../lib/localDevCommands";
import {
  clearStoredPlatformUserId,
  getPlatformUserId,
  PLATFORM_USER_STORAGE_KEY,
  setStoredPlatformUserId,
} from "../lib/platformIdentity";
import { PageHeader } from "../components/ds/PageHeader";
import LanguageSwitcher from "../components/LanguageSwitcher";

export default function Settings() {
  const { t } = useTranslation();
  const configured = getConfiguredApiBase();
  const [metaBlock, setMetaBlock] = useState<string | null>(null);
  const [metaErr, setMetaErr] = useState<string | null>(null);
  const [platformUserDraft, setPlatformUserDraft] = useState("");
  const [platformUserEffective, setPlatformUserEffective] = useState(() => getPlatformUserId());

  const syncPlatformUserFromStorage = () => {
    setPlatformUserEffective(getPlatformUserId());
    try {
      const raw = localStorage.getItem(PLATFORM_USER_STORAGE_KEY);
      setPlatformUserDraft(raw ?? "");
    } catch {
      setPlatformUserDraft("");
    }
  };

  useEffect(() => {
    syncPlatformUserFromStorage();
  }, []);

  useEffect(() => {
    let cancelled = false;
    getMeta()
      .then((m) => {
        if (cancelled) return;
        const lines = [
          `telemetry_mode: ${m.telemetry_mode}`,
          m.mjcf_default ? `mjcf_default: ${m.mjcf_default}` : null,
          typeof m.platform_worker_enabled === "boolean"
            ? `platform_worker_enabled: ${m.platform_worker_enabled}`
            : null,
          typeof m.job_timeout_sec === "number" ? `job_timeout_sec: ${m.job_timeout_sec}` : null,
        ].filter(Boolean) as string[];
        setMetaBlock(lines.join("\n"));
        setMetaErr(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setMetaBlock(null);
        setMetaErr(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="settings-page">
      <PageHeader title={t("settings.title")} description={t("settings.lead")} />

      <section className="settings-section" aria-labelledby="settings-api-heading">
        <h3 id="settings-api-heading">{t("settings.apiBaseTitle")}</h3>
        {configured ? (
          <>
            <p className="muted">{t("settings.apiBaseRemote")}</p>
            <div className="settings-kv">{configured}</div>
          </>
        ) : (
          <p className="muted">
            <Trans i18nKey="settings.apiBaseSameOrigin" components={{ c1: <code>VITE_API_BASE</code> }} />
          </p>
        )}
      </section>

      <section className="settings-section" aria-labelledby="settings-platform-user-heading">
        <h3 id="settings-platform-user-heading">{t("settings.platformUserTitle")}</h3>
        <p className="muted">
          <Trans
            i18nKey="settings.platformUserHint"
            components={{
              c1: <code>X-User-Id</code>,
              c2: <code>VITE_PLATFORM_USER_ID</code>,
            }}
          />
        </p>
        <p className="muted">{t("settings.platformUserEffectiveLabel")}</p>
        <div className="settings-kv" aria-live="polite">
          {platformUserEffective}
        </div>
        <label className="settings-platform-user-label" htmlFor="settings-platform-user-input">
          {t("settings.platformUserInputLabel")}
        </label>
        <div className="settings-platform-user-row">
          <input
            id="settings-platform-user-input"
            className="settings-platform-user-input"
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={platformUserDraft}
            onChange={(e) => setPlatformUserDraft(e.target.value)}
            placeholder={t("settings.platformUserPlaceholder")}
          />
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              setStoredPlatformUserId(platformUserDraft);
              syncPlatformUserFromStorage();
            }}
          >
            {t("settings.platformUserSave")}
          </button>
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              clearStoredPlatformUserId();
              syncPlatformUserFromStorage();
            }}
          >
            {t("settings.platformUserReset")}
          </button>
        </div>
      </section>

      <section className="settings-section" aria-labelledby="settings-local-dev-heading">
        <h3 id="settings-local-dev-heading">{t("settings.localDevTitle")}</h3>
        <p className="muted">{t("settings.localDevLead")}</p>
        <p className="muted">{t("settings.localDevTelemetryNote")}</p>
        <div className="settings-local-dev-actions">
          <button
            type="button"
            className="button secondary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(LOCAL_BACKEND_START);
                toast.success(t("settings.copyOk"));
              } catch {
                toast.error(t("settings.copyFail"));
              }
            }}
          >
            {t("settings.copyBackend")}
          </button>
          <button
            type="button"
            className="button secondary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(LOCAL_SIMULATOR_START);
                toast.success(t("settings.copyOk"));
              } catch {
                toast.error(t("settings.copyFail"));
              }
            }}
          >
            {t("settings.copySimulator")}
          </button>
        </div>
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          {t("settings.localDevHint")}
        </p>
      </section>

      <section className="settings-section" aria-labelledby="settings-lang-heading">
        <h3 id="settings-lang-heading">{t("settings.languageTitle")}</h3>
        <p className="muted">{t("settings.languageHint")}</p>
        <LanguageSwitcher />
      </section>

      <section className="settings-section" aria-labelledby="settings-docs-heading">
        <h3 id="settings-docs-heading">{t("settings.docsTitle")}</h3>
        <ul className="settings-docs-list">
          <li>{t("settings.docsUi")}</li>
          <li>{t("settings.docsWeb")}</li>
          <li>
            <Trans
              i18nKey="settings.docsFaq"
              components={{
                link: <Link to="/help" />,
                c1: <code />,
                c2: <code />,
              }}
            />
          </li>
        </ul>
      </section>

      <section className="settings-section" aria-labelledby="settings-about-heading">
        <h3 id="settings-about-heading">{t("settings.aboutTitle")}</h3>
        <p className="muted">{t("settings.frontendVersion", { version: __APP_VERSION__ })}</p>
        <p className="muted">{t("settings.backendMetaHint")}</p>
        {metaErr ? <p className="muted">{t("settings.backendMetaErr", { error: metaErr })}</p> : null}
        {metaBlock ? <pre className="settings-kv">{metaBlock}</pre> : null}
      </section>
    </div>
  );
}
