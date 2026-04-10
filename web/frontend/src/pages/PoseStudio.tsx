import { Trans, useTranslation } from "react-i18next";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "../components/ds/PageHeader";
import JointTelemetryRow from "../components/JointTelemetryRow";
import type { DisplayUnit, JointViewMode } from "../lib/jointRowDisplay";
import JointWasmSliderRow from "../components/JointWasmSliderRow";
import MuJoCoG1Viewer from "../components/mujoco/MuJoCoG1Viewer";
import RobotDiagram from "../components/RobotDiagram";
import { TelemetryDdsHints } from "../components/TelemetryDdsHints";
import {
  getJoints,
  postJointRelease,
  postJointTargets,
  savePoseDraft,
  telemetryWebSocketUrl,
} from "../api/client";
import { useBackendStatus } from "../context/BackendStatus";
import { useApiMeta } from "../hooks/useApiMeta";
import { useTelemetryWebSocket } from "../hooks/useTelemetryWebSocket";
import { SKILL_KEYS_IN_JOINT_MAP_ORDER } from "../mujoco/jointMapping";
import { jointRangeRad, qposToSkillJointAngles } from "../mujoco/qposToSkillAngles";
import { isDdsTelemetryMode } from "../lib/telemetryMode";
import {
  buildKeyframesDocumentFromJointRad,
  KEYFRAMES_PREFILL_STATE_KEY,
  stringifyKeyframesDocument,
} from "../lib/poseAuthoringBridge";
import type { JointAngles } from "../lib/telemetryTypes";
import { JOINT_SLIDER_RAD_MAX, JOINT_SLIDER_RAD_MIN } from "../lib/telemetryTypes";
import { getTargetAngles } from "../lib/telemetryTypes";
import {
  defaultJointMapFromSkillKeys,
  WASM_FALLBACK_JOINT_INDICES,
} from "../lib/wasmJointLayoutFallback";

type PoseSource = "telemetry" | "wasm";

const FALLBACK_JOINT_MAP = defaultJointMapFromSkillKeys();

const COMMAND_JOINT_COUNT = 29;

function isFullCommandMap(m: JointAngles): boolean {
  for (let i = 0; i < COMMAND_JOINT_COUNT; i++) {
    const v = m[String(i)];
    if (typeof v !== "number" || !Number.isFinite(v)) return false;
  }
  return true;
}

function buildFullPoseMapFromMerged(merged: JointAngles): JointAngles {
  const out: JointAngles = {};
  for (let i = 0; i < COMMAND_JOINT_COUNT; i++) {
    const k = String(i);
    const v = merged[k];
    out[k] = typeof v === "number" && Number.isFinite(v) ? v : 0;
  }
  return out;
}

export default function PoseStudio() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [groups, setGroups] = useState<{ name: string; indices: number[] }[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<JointViewMode>("slider");
  const [expert, setExpert] = useState(false);
  const [unit, setUnit] = useState<DisplayUnit>("deg");
  const [filterGroupName, setFilterGroupName] = useState<string | null>(null);
  const [selectedJointIndex, setSelectedJointIndex] = useState<number | null>(null);

  const [poseSource, setPoseSource] = useState<PoseSource>("telemetry");
  const setPoseSourceFromUser = useCallback((s: PoseSource) => {
    setPoseSource(s);
  }, []);

  const [wasmJointRad, setWasmJointRad] = useState<JointAngles>({});
  const [wasmRanges, setWasmRanges] = useState<Record<string, { min: number; max: number }>>({});
  const [wasmReady, setWasmReady] = useState(false);
  const [wasmViewerError, setWasmViewerError] = useState<string | null>(null);

  const apiMeta = useApiMeta();
  const { status: backendStatus, initialCheckDone } = useBackendStatus();
  const wsEnabled = initialCheckDone && backendStatus === "ok";
  const wsUrl = telemetryWebSocketUrl();
  const { status, lastFrame, lastCloseCode, reconnectAttempt, reconnectNow } =
    useTelemetryWebSocket(wsUrl, { enabled: wsEnabled });
  const ddsTelemetry = isDdsTelemetryMode(apiMeta?.telemetry_mode);
  const jointCommandEnabled = apiMeta?.joint_command_enabled === true;
  const jointCommandActive =
    jointCommandEnabled && poseSource === "telemetry" && lastFrame != null;

  const [commandRadByIndex, setCommandRadByIndex] = useState<JointAngles>({});
  const [undoSnapshot, setUndoSnapshot] = useState<JointAngles | null>(null);
  const commandMapRef = useRef<JointAngles>({});
  const commandFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mergedJointsRadRef = useRef<JointAngles | null>(null);

  useEffect(() => {
    commandMapRef.current = commandRadByIndex;
  }, [commandRadByIndex]);

  const mergedJointsRad = useMemo(() => {
    if (!lastFrame) return null;
    const base = { ...lastFrame.joints };
    const targetMap = getTargetAngles(lastFrame);
    if (targetMap) {
      for (const [k, v] of Object.entries(targetMap)) {
        if (typeof v === "number" && Number.isFinite(v)) base[k] = v;
      }
    }
    return Object.keys(base).length > 0 ? base : null;
  }, [lastFrame]);

  mergedJointsRadRef.current = mergedJointsRad;

  useEffect(() => {
    if (poseSource !== "telemetry") {
      setCommandRadByIndex({});
      commandMapRef.current = {};
      setUndoSnapshot(null);
    }
  }, [poseSource]);

  useEffect(() => {
    if (apiMeta === null) return;
    if (apiMeta.joint_command_enabled !== false) return;
    setCommandRadByIndex({});
    commandMapRef.current = {};
    setUndoSnapshot(null);
  }, [apiMeta]);

  const postFullTargetsFromRef = useCallback(() => {
    const m = commandMapRef.current;
    const joints_deg: Record<string, number> = {};
    for (const [k, rad] of Object.entries(m)) {
      if (typeof rad === "number" && Number.isFinite(rad)) {
        joints_deg[k] = (rad * 180) / Math.PI;
      }
    }
    return postJointTargets({ joints_deg });
  }, []);

  const scheduleCommandFlush = useCallback(() => {
    if (!jointCommandEnabled) return;
    if (commandFlushTimerRef.current != null) return;
    commandFlushTimerRef.current = setTimeout(() => {
      commandFlushTimerRef.current = null;
      if (!isFullCommandMap(commandMapRef.current)) return;
      void postFullTargetsFromRef().catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        toast.error(t("pose.commandSendFail"), { description: msg });
      });
    }, 90);
  }, [jointCommandEnabled, postFullTargetsFromRef, t]);

  const flushJointCommandsNow = useCallback(() => {
    if (commandFlushTimerRef.current != null) {
      clearTimeout(commandFlushTimerRef.current);
      commandFlushTimerRef.current = null;
    }
    if (!jointCommandEnabled || !isFullCommandMap(commandMapRef.current)) return;
    void postFullTargetsFromRef().catch((e) => {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(t("pose.commandSendFail"), { description: msg });
    });
  }, [jointCommandEnabled, postFullTargetsFromRef, t]);

  const handleCommandRad = useCallback(
    (indexKey: string, rad: number) => {
      const merged = mergedJointsRadRef.current;
      const prev = commandMapRef.current;
      let base: JointAngles;
      if (isFullCommandMap(prev)) {
        setUndoSnapshot({ ...prev });
        base = { ...prev };
      } else {
        if (!merged) return;
        base = buildFullPoseMapFromMerged(merged);
        setUndoSnapshot({ ...base });
      }
      const next = { ...base, [indexKey]: rad };
      commandMapRef.current = next;
      setCommandRadByIndex(next);
      scheduleCommandFlush();
    },
    [scheduleCommandFlush]
  );

  const undoLastJointChange = useCallback(() => {
    if (!undoSnapshot) return;
    const restored = { ...undoSnapshot };
    commandMapRef.current = restored;
    setCommandRadByIndex(restored);
    setUndoSnapshot(null);
    flushJointCommandsNow();
  }, [flushJointCommandsNow, undoSnapshot]);

  const syncCommandsFromTelemetry = useCallback(() => {
    const merged = mergedJointsRadRef.current;
    if (!merged || !jointCommandEnabled) return;
    const next = buildFullPoseMapFromMerged(merged);
    const prev = commandMapRef.current;
    if (isFullCommandMap(prev)) {
      setUndoSnapshot({ ...prev });
    } else {
      setUndoSnapshot(null);
    }
    commandMapRef.current = next;
    setCommandRadByIndex(next);
    flushJointCommandsNow();
  }, [flushJointCommandsNow, jointCommandEnabled]);

  const releaseJointHold = useCallback(async () => {
    try {
      await postJointRelease();
      setCommandRadByIndex({});
      commandMapRef.current = {};
      setUndoSnapshot(null);
      toast.success(t("pose.releaseOk"));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(t("pose.releaseFail"), { description: msg });
    }
  }, [t]);

  useEffect(() => {
    return () => {
      if (commandFlushTimerRef.current != null) {
        clearTimeout(commandFlushTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    void getJoints()
      .then((j) => {
        setGroups(j.groups);
        setNames(j.joint_map);
        setLoadError(null);
      })
      .catch((e) => setLoadError(String(e)));
  }, []);

  useEffect(() => {
    if (poseSource !== "wasm") {
      setWasmReady(false);
      setWasmViewerError(null);
    }
  }, [poseSource]);

  const targetMap = lastFrame ? getTargetAngles(lastFrame) : undefined;
  const hasTargetChannel = Boolean(targetMap && Object.keys(targetMap).length > 0);

  const mergedForExport = useMemo(() => {
    if (poseSource === "wasm") {
      if (!wasmReady) return null;
      for (const k of SKILL_KEYS_IN_JOINT_MAP_ORDER) {
        const v = wasmJointRad[k];
        if (typeof v !== "number" || !Number.isFinite(v)) return null;
      }
      return wasmJointRad;
    }
    if (jointCommandActive && isFullCommandMap(commandRadByIndex)) {
      return commandRadByIndex;
    }
    return mergedJointsRad;
  }, [poseSource, wasmReady, wasmJointRad, mergedJointsRad, jointCommandActive, commandRadByIndex]);

  const sendKeyframesTo = useCallback(
    (path: "/authoring" | "/pipeline") => {
      if (!mergedForExport) {
        toast.error(
          poseSource === "wasm" ? t("pose.exportKeyframesWasmNotReady") : t("pose.exportKeyframesNoTelemetry")
        );
        return;
      }
      const doc = buildKeyframesDocumentFromJointRad(mergedForExport, {
        timestampS: poseSource === "wasm" ? 0 : (lastFrame?.timestamp_s ?? 0),
      });
      const json = stringifyKeyframesDocument(doc).trimEnd();
      navigate(path, { state: { [KEYFRAMES_PREFILL_STATE_KEY]: json } });
      toast.success(t("pose.exportKeyframesOk"));
    },
    [lastFrame?.timestamp_s, mergedForExport, navigate, poseSource, t]
  );

  const saveWasmDraft = useCallback(async () => {
    if (!mergedForExport) {
      toast.error(t("pose.saveDraftNoPose"));
      return;
    }
    const raw = window.prompt(t("pose.saveDraftPrompt"));
    if (raw == null) return;
    const name = raw.trim();
    if (!name) {
      toast.error(t("pose.saveDraftEmptyName"));
      return;
    }
    try {
      const doc = buildKeyframesDocumentFromJointRad(mergedForExport, { timestampS: 0 });
      const { path } = await savePoseDraft({ name, document: doc });
      toast.success(t("pose.saveDraftOk", { path }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(t("pose.saveDraftFail"), { description: msg });
    }
  }, [mergedForExport, t]);

  const effectiveNames = useMemo(() => {
    let n = 0;
    for (const k of Object.keys(names)) {
      if (names[k]) n += 1;
    }
    return n >= 29 ? names : FALLBACK_JOINT_MAP;
  }, [names]);

  const wasmFallbackGroups = useMemo(
    () => [
      { name: t("pose.fallbackGroups.leftArm"), indices: [...WASM_FALLBACK_JOINT_INDICES.leftArm] },
      { name: t("pose.fallbackGroups.rightArm"), indices: [...WASM_FALLBACK_JOINT_INDICES.rightArm] },
      { name: t("pose.fallbackGroups.torso"), indices: [...WASM_FALLBACK_JOINT_INDICES.torso] },
      { name: t("pose.fallbackGroups.legs"), indices: [...WASM_FALLBACK_JOINT_INDICES.legs] },
    ],
    [t]
  );

  const effectiveGroups = useMemo(
    () => (groups.length > 0 ? groups : wasmFallbackGroups),
    [groups, wasmFallbackGroups]
  );

  /** API /api/joints still loading — do not block the diagram; effectiveGroups uses wasm fallback until then. */
  const jointsApiLoading = groups.length === 0 && loadError === null;

  const onWasmReady = useCallback(
    ({ model, data }: { model: unknown; data: unknown }) => {
      const ranges: Record<string, { min: number; max: number }> = {};
      for (let i = 0; i < 29; i++) {
        const sk = effectiveNames[String(i)];
        if (!sk) continue;
        const r = jointRangeRad(model as never, sk);
        if (r) ranges[sk] = r;
      }
      setWasmRanges(ranges);
      setWasmJointRad(qposToSkillJointAngles(model as never, data as { qpos: Float64Array }));
      setWasmReady(true);
      setWasmViewerError(null);
    },
    [effectiveNames]
  );

  const onWasmJointChange = useCallback((skillKey: string, rad: number) => {
    setWasmJointRad((prev) => ({ ...prev, [skillKey]: rad }));
  }, []);

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

  const filteredGroups =
    filterGroupName == null
      ? effectiveGroups
      : effectiveGroups.filter((g) => g.name === filterGroupName);

  const dash = t("common.dash");

  return (
    <div className="pose-studio-page">
      <PageHeader title={t("pose.title")} description={t("pose.lead")} />

      <div className="pose-studio-layout">
        <section
          className={`pose-studio-visual panel${poseSource === "wasm" ? " pose-studio-visual--wasm" : ""}`}
          aria-label={t("pose.robotDiagramAria")}
        >
          {poseSource === "telemetry" ? (
            <>
              {jointsApiLoading && (
                <p className="muted" style={{ marginBottom: 10 }}>
                  {t("pose.loadingGroups")}
                </p>
              )}
              <RobotDiagram
                groups={effectiveGroups}
                selectedGroupName={filterGroupName}
                activeJointIndex={selectedJointIndex}
                onSelectZone={(name) => {
                  setFilterGroupName(name);
                  setSelectedJointIndex(null);
                }}
              />
            </>
          ) : (
            <div className="pose-studio-wasm-host">
              <Suspense fallback={<p className="muted">{t("pose.wasmLoading")}</p>}>
                <MuJoCoG1Viewer
                  jointRad={wasmJointRad}
                  onReady={onWasmReady}
                  onError={(e) => {
                    setWasmViewerError(e.message);
                    setWasmReady(false);
                  }}
                />
              </Suspense>
            </div>
          )}
        </section>

        <div className="pose-studio-sidebar">
      <div className="pose-studio-toolbar panel" style={{ padding: 12 }}>
        <div className="tabs" role="tablist" aria-label={t("pose.sourceAria")}>
          <button
            type="button"
            className={poseSource === "telemetry" ? "active" : ""}
            onClick={() => setPoseSourceFromUser("telemetry")}
          >
            {t("pose.sourceTelemetry")}
          </button>
          <button
            type="button"
            className={poseSource === "wasm" ? "active" : ""}
            onClick={() => setPoseSourceFromUser("wasm")}
          >
            {t("pose.sourceWasm")}
          </button>
        </div>
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
        <label className="row" style={{ gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={expert} onChange={(e) => setExpert(e.target.checked)} />
          <span className="tag-secondary">{t("telemetry.expertLabel")}</span>
          <span className="muted" style={{ fontSize: "0.82rem", maxWidth: 280 }}>
            {t("pose.expertToolbarHint")}
          </span>
        </label>
        <div className="tabs" role="tablist" aria-label={t("telemetry.unitsAria")}>
          <button type="button" className={unit === "rad" ? "active" : ""} onClick={() => setUnit("rad")}>
            rad
          </button>
          <button type="button" className={unit === "deg" ? "active" : ""} onClick={() => setUnit("deg")}>
            °
          </button>
        </div>
        {poseSource === "telemetry" && (
          <button type="button" className="secondary" onClick={reconnectNow}>
            {t("telemetry.reconnect")}
          </button>
        )}
        {jointCommandActive && (
          <>
            <button
              type="button"
              className="secondary"
              disabled={undoSnapshot == null}
              onClick={undoLastJointChange}
            >
              {t("pose.undo")}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={mergedJointsRad == null}
              onClick={syncCommandsFromTelemetry}
            >
              {t("pose.syncFromTelemetry")}
            </button>
            <button type="button" className="secondary" onClick={() => void releaseJointHold()}>
              {t("pose.releaseMotors")}
            </button>
          </>
        )}
        <span className="muted" style={{ fontSize: "0.82rem" }}>
          {t("pose.exportKeyframesHint")}
        </span>
        <button
          type="button"
          className="secondary"
          disabled={!mergedForExport}
          onClick={() => sendKeyframesTo("/authoring")}
        >
          {t("pose.sendToAuthoring")}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={!mergedForExport}
          onClick={() => sendKeyframesTo("/pipeline")}
        >
          {t("pose.sendToPipeline")}
        </button>
        {poseSource === "wasm" && (
          <button type="button" className="secondary" disabled={!mergedForExport} onClick={() => void saveWasmDraft()}>
            {t("pose.saveDraft")}
          </button>
        )}
        {filterGroupName != null && (
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setFilterGroupName(null);
            }}
          >
            {t("pose.allGroups")}
          </button>
        )}
      </div>

      {poseSource === "telemetry" ? (
        <div className="panel pose-studio-ws">
          {!jointCommandEnabled && (
            <p className="muted" style={{ marginBottom: 10, maxWidth: 720 }}>
              <Trans
                i18nKey="pose.telemetryReadonlySlidersHint"
                components={{
                  strong: <strong />,
                  c1: <code>POST /api/joints/targets</code>,
                }}
              />
            </p>
          )}
          {jointCommandEnabled && !lastFrame && (
            <p className="muted" style={{ marginBottom: 10 }}>
              {t("pose.commandWaitTelemetry")}
            </p>
          )}
          {jointCommandActive && (
            <p className="muted" style={{ marginBottom: 10, maxWidth: 720 }}>
              <Trans
                i18nKey="pose.commandModeBanner"
                components={{
                  c1: <code>POST /api/joints/targets</code>,
                }}
              />
            </p>
          )}
          <TelemetryDdsHints
            ddsMode={ddsTelemetry}
            wsStatus={status}
            reconnectAttempt={reconnectAttempt}
            lastCloseCode={lastCloseCode}
          />
          <p className="telemetry-status">
            {t("pose.telemetryPrefix")}{" "}
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
      ) : (
        <div className="panel pose-studio-ws">
          <p className="muted">{t("pose.wasmLead")}</p>
          {loadError && (
            <p className="muted" style={{ marginTop: 8 }}>
              <Trans
                i18nKey="pose.jointsApiOfflineHint"
                components={{ c1: <code>GET /api/joints</code> }}
              />
            </p>
          )}
          {wasmViewerError && <p className="err">{wasmViewerError}</p>}
        </div>
      )}

        <aside className="pose-studio-panel panel" aria-label={t("pose.jointsPanelAria")}>
          {poseSource === "wasm" && !wasmReady && !wasmViewerError && (
            <p className="muted">{t("pose.wasmSlidersHint")}</p>
          )}
          {filteredGroups.map((g) => (
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
                      {poseSource === "telemetry" && hasTargetChannel && <th>{t("telemetry.thTarget")}</th>}
                      {poseSource === "telemetry" && jointCommandActive && (
                        <th>{t("pose.commandColumn")}</th>
                      )}
                      <th>
                        {poseSource === "telemetry" && hasTargetChannel
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
                      const label = effectiveNames[key] ?? dash;
                      const skillKey = label;
                      if (poseSource === "wasm") {
                        const actualRad =
                          typeof wasmJointRad[skillKey] === "number" ? wasmJointRad[skillKey] : undefined;
                        return (
                          <tr
                            key={i}
                            className={selectedJointIndex === i ? "joint-row-selected" : undefined}
                            onClick={() => {
                              setSelectedJointIndex(i);
                              setFilterGroupName(g.name);
                            }}
                            style={{ cursor: "pointer" }}
                          >
                            {expert && (
                              <>
                                <td className="num">{i}</td>
                                <td className="mono muted">{label}</td>
                              </>
                            )}
                            {!expert && <td>{label}</td>}
                            <td className="num">
                              {actualRad !== undefined
                                ? unit === "deg"
                                  ? `${((actualRad * 180) / Math.PI).toFixed(2)}°`
                                  : actualRad.toFixed(4)
                                : dash}
                            </td>
                          </tr>
                        );
                      }
                      const commandRadForRow = jointCommandActive
                        ? isFullCommandMap(commandRadByIndex)
                          ? typeof commandRadByIndex[key] === "number"
                            ? commandRadByIndex[key]!
                            : 0
                          : typeof lastFrame?.joints[key] === "number"
                            ? lastFrame.joints[key]!
                            : 0
                        : undefined;
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
                          isSelected={selectedJointIndex === i}
                          onActivate={() => {
                            setSelectedJointIndex(i);
                            setFilterGroupName(g.name);
                          }}
                          commandMode={jointCommandActive}
                          commandValueRad={commandRadForRow}
                          onCommandRadChange={
                            jointCommandActive ? (rad) => handleCommandRad(key, rad) : undefined
                          }
                        />
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div>
                  {g.indices.map((i) => {
                    const key = String(i);
                    const label = effectiveNames[key] ?? dash;
                    const skillKey = label;
                    if (poseSource === "wasm") {
                      const r = wasmRanges[skillKey];
                      const lo = r?.min ?? JOINT_SLIDER_RAD_MIN;
                      const hi = r?.max ?? JOINT_SLIDER_RAD_MAX;
                      const v = wasmJointRad[skillKey] ?? 0;
                      return (
                        <JointWasmSliderRow
                          key={i}
                          jointIndex={i}
                          label={label}
                          skillKey={skillKey}
                          valueRad={v}
                          minRad={lo}
                          maxRad={hi}
                          unit={unit}
                          expert={expert}
                          isSelected={selectedJointIndex === i}
                          onActivate={() => {
                            setSelectedJointIndex(i);
                            setFilterGroupName(g.name);
                          }}
                          onChangeRad={onWasmJointChange}
                          numberInputAriaLabel={t("pose.commandValueAria", { label })}
                        />
                      );
                    }
                    const commandRadForRow = jointCommandActive
                      ? isFullCommandMap(commandRadByIndex)
                        ? typeof commandRadByIndex[key] === "number"
                          ? commandRadByIndex[key]!
                          : 0
                        : typeof lastFrame?.joints[key] === "number"
                          ? lastFrame.joints[key]!
                          : 0
                      : undefined;
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
                        isSelected={selectedJointIndex === i}
                        onActivate={() => {
                          setSelectedJointIndex(i);
                          setFilterGroupName(g.name);
                        }}
                        commandMode={jointCommandActive}
                        commandValueRad={commandRadForRow}
                        onCommandRadChange={
                          jointCommandActive ? (rad) => handleCommandRad(key, rad) : undefined
                        }
                      />
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </aside>
        </div>
      </div>
    </div>
  );
}
