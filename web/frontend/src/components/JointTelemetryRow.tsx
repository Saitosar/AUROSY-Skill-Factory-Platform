import { useTranslation } from "react-i18next";
import JointAngleRow from "./JointAngleRow";
import type { DisplayUnit, JointViewMode } from "../lib/jointRowDisplay";
import { JOINT_SLIDER_RAD_MAX, JOINT_SLIDER_RAD_MIN } from "../lib/telemetryTypes";

export type { DisplayUnit, JointViewMode } from "../lib/jointRowDisplay";

const RAD2DEG = 180 / Math.PI;
const DEG2RAD = Math.PI / 180;

function formatAngle(rad: number, unit: DisplayUnit): string {
  if (unit === "deg") return `${(rad * RAD2DEG).toFixed(2)}°`;
  return rad.toFixed(4);
}

function clampRad(r: number): number {
  return Math.min(JOINT_SLIDER_RAD_MAX, Math.max(JOINT_SLIDER_RAD_MIN, r));
}

function clampCommandRad(r: number, lo: number, hi: number): number {
  const a = Math.min(lo, hi);
  const b = Math.max(lo, hi);
  return Math.min(b, Math.max(a, r));
}

export type JointTelemetryRowProps = {
  jointIndex: number;
  /** Human-readable label from joint_map */
  label: string;
  actualRad: number | undefined;
  targetRad: number | undefined;
  unit: DisplayUnit;
  expert: boolean;
  mode: JointViewMode;
  /** When true, table shows target column / slider shows target marker text */
  hasTargetChannel: boolean;
  /** Highlight row (e.g. linked from pose diagram) */
  isSelected?: boolean;
  /** Table / slider row click */
  onActivate?: () => void;
  /** When set with onCommandRadChange, user can edit commanded angle (telemetry + backend joint API). */
  commandMode?: boolean;
  commandValueRad?: number;
  onCommandRadChange?: (rad: number) => void;
  commandMinRad?: number;
  commandMaxRad?: number;
};

export default function JointTelemetryRow({
  jointIndex,
  label,
  actualRad,
  targetRad,
  unit,
  expert,
  mode,
  hasTargetChannel,
  isSelected,
  onActivate,
  commandMode,
  commandValueRad,
  onCommandRadChange,
  commandMinRad = JOINT_SLIDER_RAD_MIN,
  commandMaxRad = JOINT_SLIDER_RAD_MAX,
}: JointTelemetryRowProps) {
  const { t } = useTranslation();
  const key = String(jointIndex);
  const dash = t("common.dash");

  const cmdLo = Math.min(commandMinRad, commandMaxRad);
  const cmdHi = Math.max(commandMinRad, commandMaxRad);

  if (mode === "table") {
    const showCommand =
      Boolean(commandMode && onCommandRadChange && typeof commandValueRad === "number");
    return (
      <tr
        className={isSelected ? "joint-row-selected" : undefined}
        onClick={onActivate}
        style={onActivate ? { cursor: "pointer" } : undefined}
      >
        {expert && (
          <>
            <td className="num">{jointIndex}</td>
            <td className="mono muted">{label}</td>
          </>
        )}
        {!expert && <td>{label}</td>}
        {hasTargetChannel && (
          <td className="num">{targetRad !== undefined ? formatAngle(targetRad, unit) : dash}</td>
        )}
        {showCommand && (
          <td
            className="num"
            onClick={(e) => {
              e.stopPropagation();
            }}
          >
            <input
              type="number"
              step={unit === "deg" ? 0.1 : 0.001}
              className="mono"
              style={{ width: "5rem", fontSize: "0.85rem" }}
              aria-label={t("pose.commandValueAria", { label })}
              value={
                unit === "deg"
                  ? Math.round(commandValueRad! * RAD2DEG * 1000) / 1000
                  : Math.round(commandValueRad! * 1e6) / 1e6
              }
              onChange={(e) => {
                const x = parseFloat(e.target.value);
                if (!Number.isFinite(x)) return;
                const rad = unit === "deg" ? x * DEG2RAD : x;
                onCommandRadChange!(clampCommandRad(rad, cmdLo, cmdHi));
              }}
            />
          </td>
        )}
        <td className="num">{actualRad !== undefined ? formatAngle(actualRad, unit) : dash}</td>
      </tr>
    );
  }

  if (
    commandMode &&
    onCommandRadChange &&
    typeof commandValueRad === "number"
  ) {
    const detail =
      actualRad !== undefined ? (
        <>
          {t("joint.actual")} {formatAngle(actualRad, unit)}
          {hasTargetChannel && targetRad !== undefined ? (
            <>
              {" · "}
              {t("joint.target")} {formatAngle(targetRad, unit)}
            </>
          ) : null}
        </>
      ) : undefined;

    return (
      <JointAngleRow
        jointIndex={jointIndex}
        label={label}
        valueRad={commandValueRad}
        minRad={cmdLo}
        maxRad={cmdHi}
        unit={unit}
        expert={expert}
        isSelected={isSelected}
        onActivate={onActivate}
        onChangeRad={(rad) => onCommandRadChange(clampCommandRad(rad, cmdLo, cmdHi))}
        detail={detail}
        numberInputAriaLabel={t("pose.commandValueAria", { label })}
      />
    );
  }

  const a = actualRad !== undefined ? clampRad(actualRad) : JOINT_SLIDER_RAD_MIN;
  const showTarget = hasTargetChannel && targetRad !== undefined;
  const valueText = actualRad !== undefined ? formatAngle(a, unit) : dash;

  return (
    <div
      className={`joint-slider-row${isSelected ? " joint-slider-row-selected" : ""}`}
      onClick={onActivate}
      style={onActivate ? { cursor: "pointer" } : undefined}
    >
      <div className="joint-slider-row-label" id={`joint-slider-label-${key}`}>
        {expert && (
          <span className="joint-slider-expert muted">
            {jointIndex} · <span className="mono">{label}</span>
          </span>
        )}
        {!expert && <span>{label}</span>}
      </div>
      <div className="joint-slider-row-control">
        <input
          className="joint-range-readonly"
          type="range"
          min={JOINT_SLIDER_RAD_MIN}
          max={JOINT_SLIDER_RAD_MAX}
          step={0.001}
          value={a}
          tabIndex={-1}
          aria-readonly="true"
          aria-labelledby={`joint-slider-label-${key}`}
          aria-valuemin={JOINT_SLIDER_RAD_MIN}
          aria-valuemax={JOINT_SLIDER_RAD_MAX}
          aria-valuenow={a}
          aria-valuetext={valueText}
        />
      </div>
      <div className="joint-slider-row-values">
        {showTarget && (
          <span className="muted">
            {t("joint.target")} {formatAngle(targetRad!, unit)}
            {" · "}
          </span>
        )}
        <span className="mono">{actualRad !== undefined ? formatAngle(actualRad, unit) : dash}</span>
      </div>
    </div>
  );
}
