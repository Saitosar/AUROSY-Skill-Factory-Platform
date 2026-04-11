import JointAngleRow from "./JointAngleRow";
import type { DisplayUnit } from "../lib/jointRowDisplay";

export type JointWasmSliderRowProps = {
  jointIndex: number;
  label: string;
  expertCanonicalLabel?: string;
  skillKey: string;
  valueRad: number;
  minRad: number;
  maxRad: number;
  unit: DisplayUnit;
  expert: boolean;
  isSelected?: boolean;
  onActivate?: () => void;
  onChangeRad: (skillKey: string, rad: number) => void;
  numberInputAriaLabel?: string;
};

export default function JointWasmSliderRow({
  jointIndex,
  label,
  expertCanonicalLabel,
  skillKey,
  valueRad,
  minRad,
  maxRad,
  unit,
  expert,
  isSelected,
  onActivate,
  onChangeRad,
  numberInputAriaLabel,
}: JointWasmSliderRowProps) {
  return (
    <JointAngleRow
      jointIndex={jointIndex}
      label={label}
      expertCanonicalLabel={expertCanonicalLabel}
      valueRad={valueRad}
      minRad={minRad}
      maxRad={maxRad}
      unit={unit}
      expert={expert}
      isSelected={isSelected}
      onActivate={onActivate}
      onChangeRad={(rad) => onChangeRad(skillKey, rad)}
      numberInputAriaLabel={numberInputAriaLabel}
    />
  );
}
