/** scenario.json for Python Scenario Studio (`high_level_motions/.../scenario.json`). */

export const SCENARIO_STUDIO_VERSION = 1 as const;

export const SCENARIO_STUDIO_SUBDIRS = ["basic_actions", "complex_actions"] as const;
export type ScenarioStudioSubdir = (typeof SCENARIO_STUDIO_SUBDIRS)[number];

/** Node as persisted and consumed by `scenario_studio.runner.run_scenario`. */
export type ScenarioStudioRuntimeNode = {
  subdir: ScenarioStudioSubdir;
  action_name: string;
  speed: number;
  repeat: number;
};

/** Full document (version + title + nodes). */
export type ScenarioStudioDocument = {
  version: typeof SCENARIO_STUDIO_VERSION;
  title: string;
  nodes: ScenarioStudioRuntimeNode[];
};

export type ScenarioStudioParseError = string;

function isSubdir(s: unknown): s is ScenarioStudioSubdir {
  return s === "basic_actions" || s === "complex_actions";
}

/** Parse and validate `scenario.json` from Scenario Studio or this web app. */
export function parseScenarioStudioDocument(raw: unknown): ScenarioStudioDocument | ScenarioStudioParseError {
  if (!raw || typeof raw !== "object") return "Expected a JSON object.";
  const o = raw as Record<string, unknown>;
  const ver = o.version;
  if (ver !== SCENARIO_STUDIO_VERSION) {
    return `Expected version=${SCENARIO_STUDIO_VERSION}, got: ${String(ver)}.`;
  }
  const title = o.title;
  if (typeof title !== "string" || !title.trim()) {
    return "Field title must be a non-empty string.";
  }
  const nodesRaw = o.nodes;
  if (!Array.isArray(nodesRaw) || nodesRaw.length === 0) {
    return "nodes must be a non-empty array.";
  }
  const nodes: ScenarioStudioRuntimeNode[] = [];
  for (let i = 0; i < nodesRaw.length; i++) {
    const item = nodesRaw[i];
    if (!item || typeof item !== "object") return `nodes[${i}]: expected an object.`;
    const n = item as Record<string, unknown>;
    if (!isSubdir(n.subdir)) {
      return `nodes[${i}]: subdir must be basic_actions or complex_actions.`;
    }
    const action_name = n.action_name;
    if (typeof action_name !== "string" || !action_name.trim()) {
      return `nodes[${i}]: action_name is required.`;
    }
    const speed = Number(n.speed);
    const repeat = Number(n.repeat);
    if (!Number.isFinite(speed) || speed <= 0) return `nodes[${i}]: speed must be a number > 0.`;
    if (!Number.isFinite(repeat) || repeat < 1 || !Number.isInteger(repeat)) {
      return `nodes[${i}]: repeat must be an integer >= 1.`;
    }
    nodes.push({
      subdir: n.subdir,
      action_name: action_name.trim(),
      speed,
      repeat: Math.floor(repeat),
    });
  }
  return { version: SCENARIO_STUDIO_VERSION, title: title.trim(), nodes };
}

export function stringifyScenarioStudioDocument(doc: ScenarioStudioDocument): string {
  return `${JSON.stringify(doc, null, 2)}\n`;
}
