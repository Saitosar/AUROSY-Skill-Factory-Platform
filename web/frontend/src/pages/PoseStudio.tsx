import { useTranslation } from "react-i18next";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "../components/ds/PageHeader";
import JointWasmSliderRow from "../components/JointWasmSliderRow";
import MuJoCoG1Viewer from "../components/mujoco/MuJoCoG1Viewer";
import { getJoints, savePoseDraft } from "../api/client";
import { SKILL_KEYS_IN_JOINT_MAP_ORDER } from "../mujoco/jointMapping";
import { jointRangeRad, qposToSkillJointAngles } from "../mujoco/qposToSkillAngles";
import {
  buildKeyframesDocumentFromPoses,
  buildSdkPoseJsonArray,
  stringifySdkPoseJson,
} from "../lib/poseAuthoringBridge";
import {
  captureFullJointAnglesSkillKeys,
  segmentDurationSec,
  smoothStepJointAnglesRad,
} from "../lib/motionInterpolation";
import type { JointAngles } from "../lib/telemetryTypes";
import { JOINT_SLIDER_RAD_MAX, JOINT_SLIDER_RAD_MIN } from "../lib/telemetryTypes";
import { getJointLabel } from "../lib/jointDisplayLabel";
import {
  defaultJointMapFromSkillKeys,
  WASM_FALLBACK_JOINT_INDICES,
} from "../lib/wasmJointLayoutFallback";

const FALLBACK_JOINT_MAP = defaultJointMapFromSkillKeys();

const MAX_SAVED_WASM_POSES = 3;
const WASM_MOTION_SPEED_RAD_S = 0.5;
const MIN_MOTION_SEGMENT_SEC = 0.05;
const KEYFRAME_TIMESTAMP_STEP_S = 0.5;

export default function PoseStudio() {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<{ name: string; indices: number[] }[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [expert, setExpert] = useState(false);
  const [filterGroupName, setFilterGroupName] = useState<string | null>(null);
  const [selectedJointIndex, setSelectedJointIndex] = useState<number | null>(null);

  const [wasmJointRad, setWasmJointRad] = useState<JointAngles>({});
  const wasmJointRadRef = useRef<JointAngles>({});
  const [wasmRanges, setWasmRanges] = useState<Record<string, { min: number; max: number }>>({});
  const [wasmReady, setWasmReady] = useState(false);
  const [wasmViewerError, setWasmViewerError] = useState<string | null>(null);
  const [savedWasmPoses, setSavedWasmPoses] = useState<JointAngles[]>([]);
  const [wasmMotionPlaying, setWasmMotionPlaying] = useState(false);
  const wasmMotionPlayingRef = useRef(false);
  const wasmMotionCancelRef = useRef(false);

  useEffect(() => {
    wasmJointRadRef.current = wasmJointRad;
  }, [wasmJointRad]);

  useEffect(() => {
    wasmMotionPlayingRef.current = wasmMotionPlaying;
  }, [wasmMotionPlaying]);

  useEffect(() => {
    void getJoints()
      .then((j) => {
        setGroups(j.groups);
        setNames(j.joint_map);
        setLoadError(null);
      })
      .catch((e) => setLoadError(String(e)));
  }, []);

  const mergedForExport = useMemo(() => {
    if (!wasmReady) return null;
    for (const k of SKILL_KEYS_IN_JOINT_MAP_ORDER) {
      const v = wasmJointRad[k];
      if (typeof v !== "number" || !Number.isFinite(v)) return null;
    }
    return wasmJointRad;
  }, [wasmReady, wasmJointRad]);

  const keyframesListForExport = useMemo(() => {
    if (!mergedForExport) return null;
    const cur = captureFullJointAnglesSkillKeys(mergedForExport);
    if (savedWasmPoses.length === 0) return [cur];
    return [cur, ...savedWasmPoses];
  }, [mergedForExport, savedWasmPoses]);

  const saveWasmDraft = useCallback(async () => {
    if (!keyframesListForExport?.length) {
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
      const doc = buildKeyframesDocumentFromPoses(keyframesListForExport, {
        timestampS: 0,
        timestampStepS: KEYFRAME_TIMESTAMP_STEP_S,
      });
      const { path } = await savePoseDraft({ name, document: doc });
      toast.success(t("pose.saveDraftOk", { path }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(t("pose.saveDraftFail"), { description: msg });
    }
  }, [keyframesListForExport, t]);

  const addWasmPose = useCallback(() => {
    if (!mergedForExport || savedWasmPoses.length >= MAX_SAVED_WASM_POSES || wasmMotionPlayingRef.current) return;
    setSavedWasmPoses((prev) => [...prev, captureFullJointAnglesSkillKeys(mergedForExport)]);
    toast.success(
      t("pose.addPoseOk", {
        n: savedWasmPoses.length + 1,
        maxSaved: MAX_SAVED_WASM_POSES,
      })
    );
  }, [mergedForExport, savedWasmPoses.length, t]);

  const clearWasmSavedPoses = useCallback(() => {
    setSavedWasmPoses([]);
    toast.success(t("pose.clearPosesOk"));
  }, [t]);

  const downloadSdkPoseJson = useCallback(() => {
    const list = keyframesListForExport;
    if (!list?.length) {
      toast.error(t("pose.sdkDownloadNoPose"));
      return;
    }
    const sdk = buildSdkPoseJsonArray(list);
    const blob = new Blob([stringifySdkPoseJson(sdk)], { type: "application/json;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "pose.json";
    a.click();
    URL.revokeObjectURL(a.href);
    toast.success(t("pose.sdkDownloadOk"));
  }, [keyframesListForExport, t]);

  const stopWasmMotion = useCallback(() => {
    wasmMotionCancelRef.current = true;
  }, []);

  const playWasmMotion = useCallback(async () => {
    if (savedWasmPoses.length === 0 || !wasmReady || wasmMotionPlayingRef.current) return;
    wasmMotionCancelRef.current = false;
    setWasmMotionPlaying(true);
    try {
      let from = captureFullJointAnglesSkillKeys(wasmJointRadRef.current);
      for (let s = 0; s < savedWasmPoses.length; s++) {
        if (wasmMotionCancelRef.current) break;
        const to = savedWasmPoses[s]!;
        const durationMs =
          segmentDurationSec(from, to, WASM_MOTION_SPEED_RAD_S, MIN_MOTION_SEGMENT_SEC) * 1000;
        await new Promise<void>((resolve) => {
          const t0 = performance.now();
          const step = (now: number) => {
            if (wasmMotionCancelRef.current) {
              resolve();
              return;
            }
            const u = Math.min(1, (now - t0) / durationMs);
            setWasmJointRad(smoothStepJointAnglesRad(from, to, u));
            if (u < 1) requestAnimationFrame(step);
            else resolve();
          };
          requestAnimationFrame(step);
        });
        from = to;
      }
    } finally {
      setWasmMotionPlaying(false);
      wasmMotionCancelRef.current = false;
    }
  }, [savedWasmPoses, wasmReady]);

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
          className="pose-studio-visual panel pose-studio-visual--wasm"
          aria-label={t("pose.wasmViewerAria")}
        >
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
        </section>

        <div className="pose-studio-sidebar">
          <aside className="pose-studio-panel panel" aria-label={t("pose.jointsPanelAria")}>
            {!wasmReady && !wasmViewerError && <p className="muted">{t("pose.wasmSlidersHint")}</p>}
            {filteredGroups.map((g) => (
              <div key={g.name} style={{ marginBottom: 24 }}>
                <h3 style={{ fontSize: "1rem", marginBottom: 12 }}>{g.name}</h3>
                <div>
                  {g.indices.map((i) => {
                    const key = String(i);
                    const skillKey = effectiveNames[key] ?? dash;
                    const displayLabel = getJointLabel(skillKey, t);
                    const r = wasmRanges[skillKey];
                    const lo = r?.min ?? JOINT_SLIDER_RAD_MIN;
                    const hi = r?.max ?? JOINT_SLIDER_RAD_MAX;
                    const v = wasmJointRad[skillKey] ?? 0;
                    return (
                      <JointWasmSliderRow
                        key={i}
                        jointIndex={i}
                        label={displayLabel}
                        expertCanonicalLabel={skillKey}
                        skillKey={skillKey}
                        valueRad={v}
                        minRad={lo}
                        maxRad={hi}
                        unit="deg"
                        expert={expert}
                        isSelected={selectedJointIndex === i}
                        onActivate={() => {
                          setSelectedJointIndex(i);
                          setFilterGroupName(g.name);
                        }}
                        onChangeRad={onWasmJointChange}
                        numberInputAriaLabel={t("pose.commandValueAria", { label: displayLabel })}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </aside>
          <div className="pose-studio-toolbar panel" style={{ padding: 12 }}>
            <label className="row" style={{ gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={expert} onChange={(e) => setExpert(e.target.checked)} />
              <span className="tag-secondary">{t("telemetry.expertLabel")}</span>
            </label>
            <button
              type="button"
              className="secondary"
              disabled={
                !mergedForExport || savedWasmPoses.length >= MAX_SAVED_WASM_POSES || wasmMotionPlaying
              }
              onClick={addWasmPose}
            >
              {t("pose.addPose")}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={savedWasmPoses.length === 0 || wasmMotionPlaying}
              onClick={clearWasmSavedPoses}
            >
              {t("pose.clearSavedPoses")}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!keyframesListForExport?.length || wasmMotionPlaying}
              onClick={downloadSdkPoseJson}
            >
              {t("pose.downloadSdkPoseJson")}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={savedWasmPoses.length === 0 || !wasmReady || wasmMotionPlaying}
              onClick={() => void playWasmMotion()}
            >
              {t("pose.createMotion")}
            </button>
            <button type="button" className="secondary" disabled={!wasmMotionPlaying} onClick={stopWasmMotion}>
              {t("pose.stopMotion")}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!mergedForExport || wasmMotionPlaying}
              onClick={() => void saveWasmDraft()}
            >
              {t("pose.saveDraft")}
            </button>
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
          {(wasmViewerError || loadError) && (
            <div
              className="pose-studio-sidebar-status panel"
              aria-live="polite"
            >
              {wasmViewerError && (
                <p className="err" style={{ margin: 0, wordBreak: "break-word" }}>
                  {wasmViewerError}
                </p>
              )}
              {loadError && (
                <p className="muted" style={{ margin: wasmViewerError ? "8px 0 0" : 0, fontSize: "0.82rem", wordBreak: "break-word" }}>
                  {loadError}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
