import { Trans, useTranslation } from "react-i18next";
import { useMemo } from "react";
import { POSE_ASSETS_ARE_PLACEHOLDER } from "../lib/poseAssets";

export type JointGroup = { name: string; indices: number[] };

export type RobotDiagramProps = {
  groups: JointGroup[];
  /** Zone filter from diagram click; null = all zones neutral emphasis */
  selectedGroupName: string | null;
  /** Joint selected from panel → highlight band that contains it */
  activeJointIndex: number | null;
  onSelectZone: (groupName: string) => void;
};

function groupForJoint(groups: JointGroup[], jointIndex: number): string | null {
  const g = groups.find((x) => x.indices.includes(jointIndex));
  return g?.name ?? null;
}

export default function RobotDiagram({
  groups,
  selectedGroupName,
  activeJointIndex,
  onSelectZone,
}: RobotDiagramProps) {
  const { t } = useTranslation();
  const emphasisName = useMemo(() => {
    if (selectedGroupName) return selectedGroupName;
    if (activeJointIndex != null) return groupForJoint(groups, activeJointIndex);
    return null;
  }, [groups, selectedGroupName, activeJointIndex]);

  const n = Math.max(1, groups.length);
  const sliceH = 100 / n;

  return (
    <div className="robot-diagram">
      <div className="robot-diagram-frame">
        {POSE_ASSETS_ARE_PLACEHOLDER && (
          <div className="pose-placeholder-banner" role="status">
            <Trans
              i18nKey="pose.placeholderBanner"
              components={{
                c1: <code>public/pose/</code>,
                c2: <code>frontend_developer_guide</code>,
              }}
            />
          </div>
        )}
        <img
          className="robot-diagram-image"
          src="/pose/robot-diagram.svg"
          alt=""
          decoding="async"
        />
        <svg
          className="robot-diagram-overlay"
          viewBox="0 0 100 100"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label={t("robotDiagram.svgAria")}
        >
          <title>{t("robotDiagram.svgTitle")}</title>
          {groups.map((g, i) => {
            const y = i * sliceH;
            const isEmphasis = emphasisName === g.name;
            return (
              <g key={g.name}>
                <rect
                  x={0}
                  y={y}
                  width={100}
                  height={sliceH}
                  fill={isEmphasis ? "rgba(0, 212, 255, 0.18)" : "rgba(148, 163, 184, 0.08)"}
                  stroke={isEmphasis ? "rgba(0, 212, 255, 0.65)" : "rgba(148, 163, 184, 0.35)"}
                  strokeWidth={0.4}
                  className="robot-diagram-hit"
                  onClick={() => onSelectZone(g.name)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelectZone(g.name);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-pressed={selectedGroupName === g.name}
                  aria-label={t("robotDiagram.zoneAria", { name: g.name })}
                />
                <text
                  x={50}
                  y={y + sliceH / 2}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="var(--text-primary)"
                  fontSize={3.2}
                  fontWeight={600}
                  style={{ pointerEvents: "none" }}
                >
                  {g.name}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <p className="muted robot-diagram-hint">
        <Trans
          i18nKey="robotDiagram.hint"
          components={{
            c1: <code>GET /api/joints</code>,
            c2: <code>public/pose/robot-diagram.svg</code>,
            c3: <code>public/pose/pose-overlay.json</code>,
          }}
        />
      </p>
    </div>
  );
}
