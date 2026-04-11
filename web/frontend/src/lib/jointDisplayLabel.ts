import type { TFunction } from "i18next";

/** Localized short label for a Skill Foundry joint key (see `pose.jointLabels` in locales). */
export function getJointLabel(skillKey: string, t: TFunction): string {
  return t(`pose.jointLabels.${skillKey}`, { defaultValue: skillKey });
}
