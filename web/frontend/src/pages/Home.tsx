import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { getMeta } from "../api/client";
import { PageHeader } from "../components/ds/PageHeader";
import { useBackendStatus } from "../context/BackendStatus";

type MetaHint = { telemetry_mode: string } | null;

const shortcuts = [
  { to: "/authoring", titleKey: "home.shortcut.authoringTitle", descKey: "home.shortcut.authoringDesc" },
  { to: "/pose", titleKey: "home.shortcut.poseTitle", descKey: "home.shortcut.poseDesc" },
  { to: "/scenarios", titleKey: "home.shortcut.scenariosTitle", descKey: "home.shortcut.scenariosDesc" },
  { to: "/pipeline", titleKey: "home.shortcut.pipelineTitle", descKey: "home.shortcut.pipelineDesc" },
  { to: "/jobs", titleKey: "home.shortcut.jobsTitle", descKey: "home.shortcut.jobsDesc" },
  { to: "/packages", titleKey: "home.shortcut.packagesTitle", descKey: "home.shortcut.packagesDesc" },
  { to: "/help", titleKey: "home.shortcut.helpTitle", descKey: "home.shortcut.helpDesc" },
] as const;

export default function Home() {
  const { t } = useTranslation();
  const { status, lastError, initialCheckDone, recheck } = useBackendStatus();
  const [metaHint, setMetaHint] = useState<MetaHint>(null);

  useEffect(() => {
    if (!initialCheckDone || status !== "ok") {
      setMetaHint(null);
      return;
    }
    let cancelled = false;
    getMeta()
      .then((m) => {
        if (!cancelled) setMetaHint({ telemetry_mode: m.telemetry_mode });
      })
      .catch(() => {
        if (!cancelled) setMetaHint(null);
      });
    return () => {
      cancelled = true;
    };
  }, [initialCheckDone, status]);

  return (
    <div className="home-page">
      <PageHeader
        title={t("home.title")}
        description={
          <Trans
            i18nKey="home.leadShort"
            components={{
              c1: <code>/api/*</code>,
            }}
          />
        }
      />

      {initialCheckDone ? (
        <div
          className={`home-status ${status === "ok" ? "home-status-ok" : "home-status-down"}`}
          role="status"
          aria-live="polite"
        >
          {status === "ok" ? (
            <>
              <span className="home-status-label">{t("home.statusOk")}</span>
              {metaHint ? (
                <span className="home-status-meta">
                  {t("home.statusTelemetryMode", { mode: metaHint.telemetry_mode })}
                </span>
              ) : null}
            </>
          ) : (
            <>
              <span className="home-status-label">{t("home.statusDownShort")}</span>
              {lastError ? (
                <span className="home-status-meta" title={lastError}>
                  {lastError.length > 120 ? `${lastError.slice(0, 117)}…` : lastError}
                </span>
              ) : null}
              <button type="button" className="home-status-retry" onClick={recheck}>
                {t("backendBanner.retry")}
              </button>
            </>
          )}
        </div>
      ) : (
        <div className="home-status" role="status">
          <span className="muted">{t("home.statusChecking")}</span>
        </div>
      )}

      <section className="home-three-tiers" aria-labelledby="home-three-tiers-heading">
        <h3 id="home-three-tiers-heading">{t("home.threeTiersTitle")}</h3>
        <p className="muted home-three-tiers-lead">{t("home.threeTiersLead")}</p>
        <ol className="home-three-tiers-list">
          <li>
            <Trans
              i18nKey="home.tier1"
              components={{
                strong: <strong />,
                lp: <Link to="/pose" />,
                la: <Link to="/authoring" />,
                lpi: <Link to="/pipeline" />,
              }}
            />
          </li>
          <li>
            <Trans
              i18nKey="home.tier2"
              components={{
                strong: <strong />,
                lj: <Link to="/jobs" />,
                lpk: <Link to="/packages" />,
              }}
            />
          </li>
          <li>
            <Trans
              i18nKey="home.tier3"
              values={{
                target: 30,
                min: 25,
                max: 35,
              }}
              components={{
                strong: <strong />,
                ls: <Link to="/scenarios" />,
                c1: <code />,
                c2: <code />,
              }}
            />
          </li>
        </ol>
      </section>

      <section className="home-train-paths" aria-labelledby="home-train-paths-heading">
        <h3 id="home-train-paths-heading">{t("home.trainPathsTitle")}</h3>
        <div className="home-train-paths-body">
          <Trans
            i18nKey="home.trainPathsBody"
            components={{
              strong1: <strong />,
              strong2: <strong />,
              lp: <Link to="/pipeline" />,
              lj: <Link to="/jobs" />,
              lpk: <Link to="/packages" />,
              lh: <Link to="/help" />,
              c1: <code />,
              c2: <code />,
            }}
          />
        </div>
      </section>

      <div className="home-shortcuts">
        {shortcuts.map((s) => (
          <Link key={s.to} to={s.to} className="home-shortcut-card">
            <p className="home-shortcut-title">{t(s.titleKey)}</p>
            <p className="home-shortcut-desc">{t(s.descKey)}</p>
          </Link>
        ))}
      </div>

      <div className="home-drafts">
        <h3>{t("home.draftsTitle")}</h3>
        <p>{t("home.draftsPlaceholder")}</p>
      </div>
    </div>
  );
}
