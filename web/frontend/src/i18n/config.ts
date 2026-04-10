import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import en from "../locales/en.json";
import ru from "../locales/ru.json";

function syncDocumentLang(lng: string) {
  const base = lng.split("-")[0] ?? "ru";
  document.documentElement.lang = base === "en" ? "en" : "ru";
}

i18n.on("languageChanged", (lng) => {
  syncDocumentLang(lng);
});

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ru: { translation: ru },
      en: { translation: en },
    },
    fallbackLng: "ru",
    supportedLngs: ["ru", "en"],
    load: "languageOnly",
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
  })
  .then(() => {
    syncDocumentLang(i18n.language);
  });

export default i18n;
