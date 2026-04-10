import { Trans, useTranslation } from "react-i18next";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "../components/ds/PageHeader";
import JointTelemetryRow from "../components/JointTelemetryRow";
import type { DisplayUnit, JointViewMode } from "../lib/jointRowDisplay";
import { TelemetryDdsHints } from "../components/TelemetryDdsHints";
import { getJoints, telemetryWebSocketUrl } from "../api/client";
import { useBackendStatus } from "../context/BackendStatus";
import { useApiMeta } from "../hooks/useApiMeta";
import { useTelemetryWebSocket } from "../hooks/useTelemetryWebSocket";
import { isDdsTelemetryMode } from "../lib/telemetryMode";
import { getTargetAngles } from "../lib/telemetryTypes";

export default function Telemetry() {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<{ name: string; indices: number[] }[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<JointViewMode>("slider");
  const [expert, setExpert] = useState(false);
  const [unit, setUnit] = useState<DisplayUnit>("rad");

  const apiMeta = useApiMeta();
  const { status: backendStatus, initialCheckDone } = useBackendStatus();
  const wsEnabled = initialCheckDone && backendStatus === "ok";
  const wsUrl = telemetryWebSocketUrl();
  const { status, lastFrame, lastCloseCode, reconnectAttempt, reconnectNow } =
    useTelemetryWebSocket(wsUrl, { enabled: wsEnabled });
  const ddsTelemetry = isDdsTelemetryMode(apiMeta?.telemetry_mode);

  useEffect(() => {
    void getJoints()
      .then((j) => {
        setGroups(j.groups);
        setNames(j.joint_map);
      })
      .catch((e) => setLoadError(String(e)));
  }, []);

  const targetMap = lastFrame ? getTargetAngles(lastFrame) : undefined;
  const hasTargetChannel = Boolean(targetMap && Object.keys(targetMap).length > 0);

  const statusLabel = useMemo(() => {
    switch (status) {
      case "connecting":
        return t("telemetry.wsConnecting");
      case "open":
        return t("telemetry.wsOpen");
      case "reconnecting":
        return reconnectAttempt > 0
          ? t("telemetry.wsReconnectingAttempt", { n: reconnectAttempt })
          : t("telemetry.wsReconnecting");
      case "error":
        return t("telemetry.wsError");
      case "idle":
        if (!initialCheckDone) return t("telemetry.wsCheckingHealth");
        if (backendStatus === "down") return t("telemetry.wsPausedNoApi");
        return t("telemetry.wsIdle");
      default:
        return status;
    }
  }, [status, reconnectAttempt, t, initialCheckDone, backendStatus]);

  return (
    <div>
      <PageHeader
        title={t("telemetry.title")}
        description={
          <Trans
            i18nKey="telemetry.lead"
            components={{
              c1: <code>/ws/telemetry</code>,
              c2: <code>GET /api/joints</code>,
            }}
          />
        }
      />

      <div className="telemetry-toolbar panel" style={{ padding: 12 }}>
        <div className="tabs" role="tablist" aria-label={t("telemetry.displayModeAria")}>
          <button
            type="button"
            className={viewMode === "table" ? "active" : ""}
            onClick={() => setViewMode("table")}
          >
            {t("telemetry.table")}
          </button>
          <button
            type="button"
            className={viewMode === "slider" ? "active" : ""}
            onClick={() => setViewMode("slider")}
          >
            {t("telemetry.sliders")}
          </button>
        </div>
        <label className="row" style={{ gap: 8 }}>
          <input type="checkbox" checked={expert} onChange={(e) => setExpert(e.target.checked)} />
          <span className="tag-secondary">{t("telemetry.expertLabel")}</span>
        </label>
        <div className="tabs" role="tablist" aria-label={t("telemetry.unitsAria")}>
          <button type="button" className={unit === "rad" ? "active" : ""} onClick={() => setUnit("rad")}>
            rad
          </button>
          <button type="button" className={unit === "deg" ? "active" : ""} onClick={() => setUnit("deg")}>
            °
          </button>
        </div>
        <button type="button" className="secondary" onClick={reconnectNow}>
          {t("telemetry.reconnect")}
        </button>
      </div>

      <div className="panel">
        <TelemetryDdsHints
          ddsMode={ddsTelemetry}
          wsStatus={status}
          reconnectAttempt={reconnectAttempt}
          lastCloseCode={lastCloseCode}
        />
        <p className="telemetry-status">
          {t("telemetry.status")}{" "}
          {status === "open" ? (
            <span className="ok">{statusLabel}</span>
          ) : status === "reconnecting" ? (
            <span className="telemetry-status-reconnect">{statusLabel}</span>
          ) : status === "error" ? (
            <span className="err">{statusLabel}</span>
          ) : (
            <span className="muted">{statusLabel}</span>
          )}
          {lastFrame?.mock !== false && lastFrame != null && (
            <span className="muted">{t("telemetry.mockSuffix")}</span>
          )}
        </p>
        {loadError && <p className="err">{loadError}</p>}
      </div>

      <div className="panel">
        {groups.map((g) => (
          <div key={g.name} style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: "1rem", marginBottom: 12 }}>{g.name}</h3>
            {viewMode === "table" ? (
              <table className="data">
                <thead>
                  <tr>
                    {expert && (
                      <>
                        <th>{t("telemetry.thIndex")}</th>
                        <th>{t("telemetry.thName")}</th>
                      </>
                    )}
                    {!expert && <th>{t("telemetry.thCaption")}</th>}
                    {hasTargetChannel && <th>{t("telemetry.thTarget")}</th>}
                    <th>
                      {hasTargetChannel
                        ? t("telemetry.thActualFact")
                        : unit === "deg"
                          ? t("telemetry.thActualDeg")
                          : t("telemetry.thActualRad")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {g.indices.map((i) => {
                    const key = String(i);
                    const label = names[key] ?? t("common.dash");
                    return (
                      <JointTelemetryRow
                        key={i}
                        jointIndex={i}
                        label={label}
                        actualRad={lastFrame?.joints[key]}
                        targetRad={targetMap?.[key]}
                        unit={unit}
                        expert={expert}
                        mode="table"
                        hasTargetChannel={hasTargetChannel}
                      />
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <div>
                {g.indices.map((i) => {
                  const key = String(i);
                  const label = names[key] ?? t("common.dash");
                  return (
                    <JointTelemetryRow
                      key={i}
                      jointIndex={i}
                      label={label}
                      actualRad={lastFrame?.joints[key]}
                      targetRad={targetMap?.[key]}
                      unit={unit}
                      expert={expert}
                      mode="slider"
                      hasTargetChannel={hasTargetChannel}
                    />
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
