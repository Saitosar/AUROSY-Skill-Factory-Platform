import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
} from "react";
import { Trans, useTranslation } from "react-i18next";
import { toast } from "sonner";
import { estimateScenario, getMidLevelActions } from "../api/client";
import { EmptyState } from "../components/ds/EmptyState";
import { PageHeader } from "../components/ds/PageHeader";
import { ValidateBanner } from "../components/ds/ValidateBanner";
import i18n from "../i18n/config";
import {
  parseScenarioStudioDocument,
  stringifyScenarioStudioDocument,
  type ScenarioStudioDocument,
  type ScenarioStudioRuntimeNode,
} from "../lib/scenarioContract";

/** Целевое окно длительности сценария (продуктовый ориентир, как в десктопном Scenario Studio). */
const TARGET_SCENARIO_SECONDS = 30;
const WARN_DURATION_MIN_SECONDS = 25;
const WARN_DURATION_MAX_SECONDS = 35;
const ESTIMATE_DEBOUNCE_MS = 500;

type CatalogAction = {
  subdir: string;
  action_name: string;
  label: string;
  keyframe_count: number;
};

type ScenarioNode = {
  id: string;
  subdir: string;
  action_name: string;
  speed: number;
  repeat: number;
  keyframe_count: number;
};

type EstimateResult = {
  nodes: {
    subdir: string;
    action_name: string;
    speed: number;
    repeat: number;
    keyframe_count: number;
    estimated_seconds: number;
  }[];
  total_estimated_seconds: number;
};

function actionKey(a: { subdir: string; action_name: string }) {
  return `${a.subdir}/${a.action_name}`;
}

function estimatePayload(nodes: ScenarioNode[]) {
  return nodes.map((n) => ({
    subdir: n.subdir,
    action_name: n.action_name,
    speed: n.speed,
    repeat: n.repeat,
    keyframe_count: n.keyframe_count,
  }));
}

type SortableRowProps = {
  node: ScenarioNode;
  index: number;
  labelFor: (subdir: string, action_name: string) => string;
  estimate: EstimateResult | null;
  dash: string;
  updateNode: (i: number, patch: Partial<Pick<ScenarioNode, "speed" | "repeat" | "keyframe_count">>) => void;
  moveNode: (i: number, delta: -1 | 1) => void;
  removeAt: (i: number) => void;
  nodesLength: number;
};

function SortableChainRow({
  node,
  index,
  labelFor,
  estimate,
  dash,
  updateNode,
  moveNode,
  removeAt,
  nodesLength,
}: SortableRowProps) {
  const { t } = useTranslation();
  const estSec = estimate?.nodes[index]?.estimated_seconds;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: node.id,
  });
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.88 : 1,
  };

  return (
    <tr ref={setNodeRef} style={style}>
      <td>{index + 1}</td>
      <td>
        <button
          type="button"
          className="scenario-chain-drag-handle"
          aria-label={t("scenario.dragHandleAria")}
          {...attributes}
          {...listeners}
        >
          ⠿
        </button>
      </td>
      <td>
        <div>{labelFor(node.subdir, node.action_name)}</div>
        <code className="muted" style={{ fontSize: 12 }}>
          {node.subdir}/{node.action_name}
        </code>
      </td>
      <td>
        <input
          type="number"
          step={0.05}
          min={0.05}
          value={node.speed}
          onChange={(e) => updateNode(index, { speed: Number(e.target.value) })}
          style={{ width: 72 }}
        />
      </td>
      <td>
        <input
          type="number"
          min={1}
          step={1}
          value={node.repeat}
          onChange={(e) =>
            updateNode(index, { repeat: Math.max(1, Math.floor(Number(e.target.value) || 1)) })
          }
          style={{ width: 64 }}
        />
      </td>
      <td>
        <input
          type="number"
          min={1}
          step={1}
          value={node.keyframe_count}
          onChange={(e) =>
            updateNode(index, {
              keyframe_count: Math.max(1, Math.floor(Number(e.target.value) || 1)),
            })
          }
          style={{ width: 72 }}
        />
      </td>
      <td>{estimate && estSec !== undefined ? `${estSec.toFixed(1)}` : dash}</td>
      <td>
        <button
          type="button"
          className="secondary"
          disabled={index === 0}
          onClick={() => moveNode(index, -1)}
          aria-label={t("scenario.moveUpAria")}
        >
          ↑
        </button>{" "}
        <button
          type="button"
          className="secondary"
          disabled={index === nodesLength - 1}
          onClick={() => moveNode(index, 1)}
          aria-label={t("scenario.moveDownAria")}
        >
          ↓
        </button>
      </td>
      <td>
        <button type="button" className="secondary" onClick={() => removeAt(index)}>
          {t("scenario.remove")}
        </button>
      </td>
    </tr>
  );
}

export default function ScenarioBuilder() {
  const { t } = useTranslation();
  const [catalog, setCatalog] = useState<CatalogAction[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogErr, setCatalogErr] = useState<string | null>(null);
  const [catalogFilter, setCatalogFilter] = useState("");

  const [defaultSpeed, setDefaultSpeed] = useState(0.5);
  const [defaultRepeat, setDefaultRepeat] = useState(1);
  const [scenarioTitle, setScenarioTitle] = useState("untitled");
  const scenarioFileInputRef = useRef<HTMLInputElement | null>(null);

  const [nodes, setNodes] = useState<ScenarioNode[]>([]);
  const [estimate, setEstimate] = useState<EstimateResult | null>(null);
  const [estimateErr, setEstimateErr] = useState<string | null>(null);
  const [estimatePending, setEstimatePending] = useState(false);
  const estimateSeq = useRef(0);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const invalidateEstimate = useCallback(() => {
    setEstimate(null);
  }, []);

  const scrollToCatalog = useCallback(() => {
    document.getElementById("scenario-catalog")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  useEffect(() => {
    setCatalogLoading(true);
    setCatalogErr(null);
    void getMidLevelActions()
      .then((r) => {
        setCatalog(r.actions);
      })
      .catch((e) => {
        setCatalogErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        setCatalogLoading(false);
      });
  }, []);

  const labelFor = useCallback(
    (subdir: string, action_name: string) => {
      const a = catalog.find((x) => x.subdir === subdir && x.action_name === action_name);
      return a?.label ?? `${subdir}/${action_name}`;
    },
    [catalog]
  );

  const filteredCatalog = useMemo(() => {
    const q = catalogFilter.trim().toLowerCase();
    if (!q) return catalog;
    return catalog.filter((a) => {
      const hay = `${a.label} ${a.subdir} ${a.action_name}`.toLowerCase();
      return hay.includes(q);
    });
  }, [catalog, catalogFilter]);

  const nodesSig = useMemo(() => JSON.stringify(nodes), [nodes]);

  const runEstimate = useCallback(async (mode: "auto" | "manual") => {
    const n = nodesRef.current;
    if (n.length === 0) {
      if (mode === "manual") setEstimateErr(t("scenario.estimateNeedNode"));
      return;
    }
    const seq = ++estimateSeq.current;
    setEstimateErr(null);
    setEstimatePending(true);
    try {
      const r = await estimateScenario(estimatePayload(n));
      if (seq !== estimateSeq.current) return;
      setEstimate(r);
    } catch (e) {
      if (seq !== estimateSeq.current) return;
      const msg = e instanceof Error ? e.message : String(e);
      setEstimateErr(msg);
      if (mode === "manual") {
        toast.error(i18n.t("toast.networkError"), { description: msg });
      }
    } finally {
      if (seq === estimateSeq.current) setEstimatePending(false);
    }
  }, [t]);

  function clearDebounce() {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  }

  useEffect(() => {
    clearDebounce();
    if (nodes.length === 0) return;
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null;
      void runEstimate("auto");
    }, ESTIMATE_DEBOUNCE_MS);
    return () => clearDebounce();
  }, [nodesSig, runEstimate]);

  function addNodeFromAction(a: CatalogAction) {
    invalidateEstimate();
    setNodes((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        subdir: a.subdir,
        action_name: a.action_name,
        speed: defaultSpeed,
        repeat: defaultRepeat,
        keyframe_count: a.keyframe_count,
      },
    ]);
  }

  function removeAt(i: number) {
    invalidateEstimate();
    setNodes((prev) => prev.filter((_, j) => j !== i));
  }

  function updateNode(i: number, patch: Partial<Pick<ScenarioNode, "speed" | "repeat" | "keyframe_count">>) {
    invalidateEstimate();
    setNodes((prev) => prev.map((n, j) => (j === i ? { ...n, ...patch } : n)));
  }

  function moveNode(i: number, delta: -1 | 1) {
    const j = i + delta;
    if (j < 0 || j >= nodes.length) return;
    invalidateEstimate();
    setNodes((prev) => {
      const next = [...prev];
      const t0 = next[i]!;
      next[i] = next[j]!;
      next[j] = t0;
      return next;
    });
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    invalidateEstimate();
    setNodes((prev) => {
      const oldIndex = prev.findIndex((n) => n.id === active.id);
      const newIndex = prev.findIndex((n) => n.id === over.id);
      if (oldIndex < 0 || newIndex < 0) return prev;
      return arrayMove(prev, oldIndex, newIndex);
    });
  }

  function estimateNow() {
    clearDebounce();
    void runEstimate("manual");
  }

  function runtimeDocFromUi(): ScenarioStudioDocument {
    return {
      version: 1,
      title: scenarioTitle.trim() || "untitled",
      nodes: nodes.map(
        (n): ScenarioStudioRuntimeNode => ({
          subdir: n.subdir as ScenarioStudioRuntimeNode["subdir"],
          action_name: n.action_name,
          speed: n.speed,
          repeat: n.repeat,
        })
      ),
    };
  }

  function nodesFromStudioDoc(
    doc: ScenarioStudioDocument,
    catalogList: CatalogAction[]
  ): ScenarioNode[] {
    const catalogByKey = new Map(catalogList.map((a) => [actionKey(a), a]));
    return doc.nodes.map((rn) => {
      const key = `${rn.subdir}/${rn.action_name}`;
      const a = catalogByKey.get(key);
      return {
        id: crypto.randomUUID(),
        subdir: rn.subdir,
        action_name: rn.action_name,
        speed: rn.speed,
        repeat: rn.repeat,
        keyframe_count: a?.keyframe_count ?? 1,
      };
    });
  }

  function downloadScenarioJson() {
    if (nodes.length === 0) {
      toast.error(t("scenario.exportNeedNodes"));
      return;
    }
    const doc = runtimeDocFromUi();
    const blob = new Blob([stringifyScenarioStudioDocument(doc)], {
      type: "application/json;charset=utf-8",
    });
    const safeName = (scenarioTitle.trim() || "scenario").replace(/[^\w\-]+/g, "_");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${safeName.slice(0, 80)}.scenario.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function copyScenarioJson() {
    if (nodes.length === 0) {
      toast.error(t("scenario.exportNeedNodes"));
      return;
    }
    try {
      await navigator.clipboard.writeText(stringifyScenarioStudioDocument(runtimeDocFromUi()).trimEnd());
      toast.success(t("scenario.copyScenarioOk"));
    } catch (e) {
      toast.error(t("scenario.copyScenarioFail"), {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  }

  function onPickScenarioFile() {
    scenarioFileInputRef.current?.click();
  }

  async function onScenarioFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const text = await file.text();
      const parsed: unknown = JSON.parse(text);
      const doc = parseScenarioStudioDocument(parsed);
      if (typeof doc === "string") {
        toast.error(t("scenario.importInvalid"), { description: doc });
        return;
      }
      setScenarioTitle(doc.title);
      setNodes(nodesFromStudioDoc(doc, catalog));
      invalidateEstimate();
      toast.success(t("scenario.importOk"));
    } catch (err) {
      toast.error(t("scenario.importInvalid"), {
        description: err instanceof Error ? err.message : String(err),
      });
    }
  }

  const warnOutsideDurationWindow =
    estimate !== null &&
    (estimate.total_estimated_seconds < WARN_DURATION_MIN_SECONDS ||
      estimate.total_estimated_seconds > WARN_DURATION_MAX_SECONDS);

  const dash = t("common.dash");

  return (
    <div>
      <PageHeader
        title={t("scenario.title")}
        description={
          <Trans
            i18nKey="scenario.lead"
            values={{
              target: TARGET_SCENARIO_SECONDS,
              min: WARN_DURATION_MIN_SECONDS,
              max: WARN_DURATION_MAX_SECONDS,
            }}
            components={{ c1: <code>mid_level_motions/*/execute.py</code> }}
          />
        }
      />

      <div className="panel" id="scenario-catalog" style={{ marginBottom: 16 }}>
        <h3 style={{ fontSize: "1rem", margin: "0 0 12px", fontWeight: 600 }}>
          {t("scenario.availableActions")}
        </h3>
        {catalogLoading && <p className="muted">{t("scenario.catalogLoading")}</p>}
        {catalogErr && <p className="err">{catalogErr}</p>}
        {!catalogLoading && !catalogErr && catalog.length === 0 && (
          <EmptyState title={t("scenario.emptyCatalogTitle")} description={t("scenario.emptyCatalogDesc")} />
        )}
        {!catalogLoading && !catalogErr && catalog.length > 0 && (
          <>
            <div className="row" style={{ flexWrap: "wrap", marginBottom: 8 }}>
              <label>
                {t("scenario.defaultsWhenAdding")} speed{" "}
                <input
                  type="number"
                  step={0.05}
                  min={0.05}
                  value={defaultSpeed}
                  onChange={(e) => setDefaultSpeed(Number(e.target.value))}
                />
              </label>
              <label>
                repeat{" "}
                <input
                  type="number"
                  min={1}
                  step={1}
                  value={defaultRepeat}
                  onChange={(e) => setDefaultRepeat(Number(e.target.value))}
                />
              </label>
              <label style={{ flex: "1 1 200px" }}>
                {t("scenario.filter")}{" "}
                <input
                  type="search"
                  placeholder={t("scenario.filterPlaceholder")}
                  value={catalogFilter}
                  onChange={(e) => setCatalogFilter(e.target.value)}
                  style={{ marginLeft: 8, minWidth: 180 }}
                />
              </label>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>{t("scenario.thLabel")}</th>
                    <th>{t("scenario.thSubdirAction")}</th>
                    <th>{t("scenario.thKeyframeCount")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filteredCatalog.map((a) => (
                    <tr key={actionKey(a)}>
                      <td>{a.label}</td>
                      <td>
                        <code>
                          {a.subdir}/{a.action_name}
                        </code>
                      </td>
                      <td>{a.keyframe_count}</td>
                      <td>
                        <button type="button" className="secondary" onClick={() => addNodeFromAction(a)}>
                          {t("scenario.addToScenario")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {filteredCatalog.length === 0 && catalog.length > 0 && (
              <p className="muted" style={{ marginTop: 8 }}>
                {t("scenario.noFilterMatch")}
              </p>
            )}
          </>
        )}
      </div>

      <div className="panel">
        <h3 style={{ fontSize: "1rem", margin: "0 0 12px", fontWeight: 600 }}>{t("scenario.chainTitle")}</h3>
        <div className="row" style={{ marginBottom: 12, flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <label className="row" style={{ gap: 8, alignItems: "center" }}>
            <span>{t("scenario.scenarioTitleLabel")}</span>
            <input
              type="text"
              value={scenarioTitle}
              onChange={(e) => setScenarioTitle(e.target.value)}
              style={{ minWidth: 200 }}
              autoComplete="off"
            />
          </label>
        </div>
        <div className="row" style={{ marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
          <button
            type="button"
            className="primary"
            disabled={estimatePending || nodes.length === 0}
            onClick={() => estimateNow()}
          >
            {estimatePending ? t("scenario.estimatePending") : t("scenario.estimate")}
          </button>
          <button type="button" className="secondary" disabled={nodes.length === 0} onClick={() => downloadScenarioJson()}>
            {t("scenario.downloadScenarioJson")}
          </button>
          <button type="button" className="secondary" disabled={nodes.length === 0} onClick={() => void copyScenarioJson()}>
            {t("scenario.copyScenarioJson")}
          </button>
          <button type="button" className="secondary" onClick={() => onPickScenarioFile()}>
            {t("scenario.loadScenarioJson")}
          </button>
          <input
            ref={scenarioFileInputRef}
            type="file"
            accept="application/json,.json"
            style={{ display: "none" }}
            onChange={(e) => void onScenarioFileChange(e)}
          />
          <span className="muted" style={{ fontSize: "0.85rem", alignSelf: "center" }}>
            {t("scenario.estimateDebounceHint", { ms: ESTIMATE_DEBOUNCE_MS })}
          </span>
        </div>
        <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0, marginBottom: 12 }}>
          {t("scenario.scenarioJsonHint")}
        </p>
        {estimateErr && <p className="err">{estimateErr}</p>}
        {nodes.length === 0 ? (
          <EmptyState
            title={t("scenario.emptyChainTitle")}
            description={t("scenario.emptyChainDesc")}
          >
            <button type="button" className="primary" onClick={scrollToCatalog}>
              {t("scenario.ctaScrollToCatalog")}
            </button>
          </EmptyState>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <table className="data">
                <thead>
                  <tr>
                    <th>{t("scenario.thNum")}</th>
                    <th aria-label={t("scenario.dragHandleAria")} />
                    <th>{t("scenario.thAction")}</th>
                    <th>{t("scenario.thSpeed")}</th>
                    <th>{t("scenario.thRepeat")}</th>
                    <th>{t("scenario.thKeyframeCountCol")}</th>
                    <th>{t("scenario.thEstimateSec")}</th>
                    <th>{t("scenario.thOrder")}</th>
                    <th />
                  </tr>
                </thead>
                <SortableContext items={nodes.map((n) => n.id)} strategy={verticalListSortingStrategy}>
                  <tbody>
                    {nodes.map((n, i) => (
                      <SortableChainRow
                        key={n.id}
                        node={n}
                        index={i}
                        labelFor={labelFor}
                        estimate={estimate}
                        dash={dash}
                        updateNode={updateNode}
                        moveNode={moveNode}
                        removeAt={removeAt}
                        nodesLength={nodes.length}
                      />
                    ))}
                  </tbody>
                </SortableContext>
              </table>
            </DndContext>
          </div>
        )}

        {estimate && (
          <div style={{ marginTop: 16 }}>
            <p>
              <Trans
                i18nKey="scenario.total"
                values={{ seconds: estimate.total_estimated_seconds.toFixed(1) }}
                components={[<strong />]}
              />
            </p>
            {warnOutsideDurationWindow && (
              <ValidateBanner variant="warning">
                {t("scenario.warnDuration", {
                  min: WARN_DURATION_MIN_SECONDS,
                  max: WARN_DURATION_MAX_SECONDS,
                  target: TARGET_SCENARIO_SECONDS,
                })}
              </ValidateBanner>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
