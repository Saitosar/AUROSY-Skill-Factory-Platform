import { useCallback, useId, useState, type ReactNode } from "react";
import type { DisplayUnit } from "../lib/jointRowDisplay";

const RAD2DEG = 180 / Math.PI;
const DEG2RAD = Math.PI / 180;

function formatAngle(rad: number, unit: DisplayUnit): string {
  if (unit === "deg") return `${(rad * RAD2DEG).toFixed(2)}°`;
  return rad.toFixed(4);
}

function clampRad(r: number, lo: number, hi: number): number {
  const a = Math.min(lo, hi);
  const b = Math.max(lo, hi);
  return Math.min(b, Math.max(a, r));
}

export type JointAngleRowProps = {
  jointIndex: number;
  label: string;
  valueRad: number;
  minRad: number;
  maxRad: number;
  unit: DisplayUnit;
  expert: boolean;
  isSelected?: boolean;
  onActivate?: () => void;
  onChangeRad: (rad: number) => void;
  /** Extra line under the value (e.g. actual vs command). */
  detail?: ReactNode;
  /** aria-label for the numeric input */
  numberInputAriaLabel?: string;
};

export default function JointAngleRow({
  jointIndex,
  label,
  valueRad,
  minRad,
  maxRad,
  unit,
  expert,
  isSelected,
  onActivate,
  onChangeRad,
  detail,
  numberInputAriaLabel,
}: JointAngleRowProps) {
  const lo = Math.min(minRad, maxRad);
  const hi = Math.max(minRad, maxRad);
  const v = clampRad(valueRad, lo, hi);
  const valueText = formatAngle(v, unit);
  const baseId = useId();
  const labelId = `${baseId}-label`;

  const [draft, setDraft] = useState<string | null>(null);

  const inputValue =
    draft !== null
      ? draft
      : unit === "deg"
        ? (v * RAD2DEG).toFixed(2)
        : v.toFixed(4);

  const commitDraft = useCallback(() => {
    if (draft === null) return;
    const t = draft.trim().replace(",", ".");
    const num = parseFloat(t);
    if (!Number.isFinite(num)) {
      setDraft(null);
      return;
    }
    const rad = unit === "deg" ? num * DEG2RAD : num;
    onChangeRad(clampRad(rad, lo, hi));
    setDraft(null);
  }, [draft, unit, lo, hi, onChangeRad]);

  return (
    <div
      className={`joint-slider-row${isSelected ? " joint-slider-row-selected" : ""}`}
      onClick={onActivate}
      style={onActivate ? { cursor: "pointer" } : undefined}
    >
      <div className="joint-slider-row-label" id={labelId}>
        {expert && (
          <span className="joint-slider-expert muted">
            {jointIndex} · <span className="mono">{label}</span>
          </span>
        )}
        {!expert && <span>{label}</span>}
      </div>
      <div className="joint-slider-row-control">
        <input
          type="range"
          min={lo}
          max={hi}
          step={0.001}
          value={v}
          aria-labelledby={labelId}
          aria-valuemin={lo}
          aria-valuemax={hi}
          aria-valuenow={v}
          aria-valuetext={valueText}
          onChange={(e) => {
            onChangeRad(Number(e.target.value));
            setDraft(null);
          }}
          onClick={(e) => e.stopPropagation()}
        />
      </div>
      <div className="joint-slider-row-values" style={{ flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
        <div className="row" style={{ gap: 8, alignItems: "center" }}>
          <input
            type="text"
            inputMode="decimal"
            className="mono"
            style={{
              width: unit === "deg" ? "4.5rem" : "5.25rem",
              fontSize: "0.85rem",
              padding: "2px 6px",
            }}
            aria-label={numberInputAriaLabel ?? `${label} value`}
            value={inputValue}
            onClick={(e) => e.stopPropagation()}
            onFocus={() => {
              setDraft(unit === "deg" ? (v * RAD2DEG).toFixed(2) : v.toFixed(4));
            }}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => commitDraft()}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                (e.target as HTMLInputElement).blur();
              }
            }}
          />
          <span className="mono">{unit === "deg" ? "°" : "rad"}</span>
        </div>
        {detail ? <div className="muted" style={{ fontSize: "0.75rem", textAlign: "right" }}>{detail}</div> : null}
      </div>
    </div>
  );
}
