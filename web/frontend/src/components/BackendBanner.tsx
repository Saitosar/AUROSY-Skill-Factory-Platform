import { Trans, useTranslation } from "react-i18next";
import { useBackendStatus } from "../context/BackendStatus";

export default function BackendBanner() {
  const { t } = useTranslation();
  const { status, lastError, initialCheckDone, recheck } = useBackendStatus();

  if (!initialCheckDone || status !== "down") return null;

  return (
    <div className="backend-banner" role="alert">
      <div className="backend-banner-inner">
        <strong>{t("backendBanner.title")}</strong>{" "}
        <span className="backend-banner-detail">
          <Trans
            i18nKey="backendBanner.detail"
            components={{ c1: <code>/api/health</code> }}
          />
          {lastError ? ` (${lastError})` : null}
        </span>
        <button type="button" className="backend-banner-retry" onClick={recheck}>
          {t("backendBanner.retry")}
        </button>
      </div>
    </div>
  );
}
