import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import type { ErrorObject } from "ajv";

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);

const cache = new Map<string, object>();

/** Expected `schema_version` from authoring JSON Schema (`properties.schema_version.const`). */
export function getExpectedSchemaVersionFromAuthoringSchema(schema: object): string | null {
  const s = schema as Record<string, unknown>;
  const props = s.properties as Record<string, unknown> | undefined;
  const sv = props?.schema_version as Record<string, unknown> | undefined;
  const c = sv?.const;
  return typeof c === "string" ? c : null;
}

export async function getExpectedAuthoringSchemaVersion(
  path: Parameters<typeof loadSchema>[0]
): Promise<string | null> {
  const schema = await loadSchema(path);
  return getExpectedSchemaVersionFromAuthoringSchema(schema);
}

export async function loadSchema(
  path: "/contracts/authoring/keyframes.schema.json" | "/contracts/authoring/motion.schema.json" | "/contracts/authoring/scenario.schema.json"
): Promise<object> {
  if (cache.has(path)) return cache.get(path)!;
  const r = await fetch(path);
  if (!r.ok) throw new Error(`schema ${path}: ${r.status}`);
  const sch = (await r.json()) as object;
  cache.set(path, sch);
  return sch;
}

export async function validateAgainstSchema(
  path: Parameters<typeof loadSchema>[0],
  data: unknown
): Promise<{ ok: true } | { ok: false; errors: string[] }> {
  const schema = await loadSchema(path);
  const validate = ajv.compile(schema);
  if (validate(data)) return { ok: true };
  const errs = (validate.errors || []) as ErrorObject[];
  const lines = errs.map((e) => `${e.instancePath || "/"} ${e.message}`);
  return { ok: false, errors: lines };
}
