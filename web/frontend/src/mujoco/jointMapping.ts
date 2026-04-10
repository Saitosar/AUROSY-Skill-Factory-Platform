/**
 * Menagerie MJCF hinge joint names in the same order as backend
 * `JOINT_MAP` indices 0..28 (Skill Foundry Phase 0 keys without `_joint` suffix).
 * @see AUROSY_creators_factory_platform/web/backend/app/joint_map.py
 */
export const MENAGERIE_JOINT_NAMES = [
  "left_hip_pitch_joint",
  "left_hip_roll_joint",
  "left_hip_yaw_joint",
  "left_knee_joint",
  "left_ankle_pitch_joint",
  "left_ankle_roll_joint",
  "right_hip_pitch_joint",
  "right_hip_roll_joint",
  "right_hip_yaw_joint",
  "right_knee_joint",
  "right_ankle_pitch_joint",
  "right_ankle_roll_joint",
  "waist_yaw_joint",
  "waist_roll_joint",
  "waist_pitch_joint",
  "left_shoulder_pitch_joint",
  "left_shoulder_roll_joint",
  "left_shoulder_yaw_joint",
  "left_elbow_joint",
  "left_wrist_roll_joint",
  "left_wrist_pitch_joint",
  "left_wrist_yaw_joint",
  "right_shoulder_pitch_joint",
  "right_shoulder_roll_joint",
  "right_shoulder_yaw_joint",
  "right_elbow_joint",
  "right_wrist_roll_joint",
  "right_wrist_pitch_joint",
  "right_wrist_yaw_joint",
] as const;

export type MenagerieJointName = (typeof MENAGERIE_JOINT_NAMES)[number];

/** Skill Foundry joint key (matches `JOINT_MAP` string values). */
export function menagerieJointToSkillKey(name: MenagerieJointName): string {
  return name.replace(/_joint$/, "");
}

export const SKILL_KEYS_IN_JOINT_MAP_ORDER = MENAGERIE_JOINT_NAMES.map(menagerieJointToSkillKey);
