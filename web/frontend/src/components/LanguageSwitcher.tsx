import { useTranslation } from "react-i18next";

export default function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const resolved = (i18n.resolvedLanguage ?? i18n.language).split("-")[0] ?? "ru";

  return (
    <div className="lang-switch" role="group" aria-label={t("lang.switchAria")}>
      <button
        type="button"
        className={`lang-switch-btn${resolved === "ru" ? " active" : ""}`}
        onClick={() => void i18n.changeLanguage("ru")}
      >
        RU
      </button>
      <button
        type="button"
        className={`lang-switch-btn${resolved === "en" ? " active" : ""}`}
        onClick={() => void i18n.changeLanguage("en")}
      >
        EN
      </button>
    </div>
  );
}
