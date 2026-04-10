import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { WsConnectionStatus } from "../hooks/useTelemetryWebSocket";

type Props = {
  ddsMode: boolean;
  wsStatus: WsConnectionStatus;
  reconnectAttempt: number;
  lastCloseCode: number | null;
};

/** F17: explain DDS telemetry expectations and unstable WebSocket when meta reports DDS mode. */
export function TelemetryDdsHints({ ddsMode, wsStatus, reconnectAttempt, lastCloseCode }: Props) {
  const { t } = useTranslation();
  const showUnstable =
    ddsMode &&
    (wsStatus === "reconnecting" || wsStatus === "error") &&
    (lastCloseCode != null || reconnectAttempt > 1);

  if (!ddsMode) return null;

  return (
    <div className="telemetry-dds-hints">
      <div className="warn-banner telemetry-dds-banner" role="note">
        <Trans
          i18nKey="telemetry.ddsModeBanner"
          components={{
            c1: <code />,
            c2: <code />,
            c3: <code />,
            strong: <strong />,
            link: <Link to="/help" />,
          }}
        />
      </div>
      {showUnstable ? (
        <p className="muted telemetry-dds-unstable" role="status">
          {t("telemetry.ddsUnstableHint", {
            code: lastCloseCode != null ? String(lastCloseCode) : "—",
          })}
        </p>
      ) : null}
    </div>
  );
}
