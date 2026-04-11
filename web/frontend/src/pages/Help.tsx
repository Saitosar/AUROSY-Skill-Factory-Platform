import { Trans, useTranslation } from "react-i18next";
import { PageHeader } from "../components/ds/PageHeader";

const FAQ_SECTIONS: { id: string; count: number }[] = [
  { id: "api", count: 4 },
  { id: "authoring", count: 3 },
  { id: "pose", count: 2 },
  { id: "scenario", count: 1 },
  { id: "pipeline", count: 3 },
  { id: "deployment", count: 5 },
  { id: "platform", count: 7 },
  { id: "skillfactory", count: 2 },
  { id: "i18n", count: 1 },
];

export default function Help() {
  const { t } = useTranslation();

  return (
    <div className="faq-page">
      <PageHeader title={t("faq.title")} description={t("faq.lead")} />

      {FAQ_SECTIONS.map((section) => (
        <section
          key={section.id}
          className="faq-section"
          aria-labelledby={`faq-${section.id}-heading`}
        >
          <h2 id={`faq-${section.id}-heading`}>{t(`faq.${section.id}.h2`)}</h2>
          <div className="faq-list">
            {Array.from({ length: section.count }, (_, i) => {
              const n = i + 1;
              const aKey = `faq.${section.id}.a${n}` as const;
              return (
                <details key={n} className="faq-details">
                  <summary>{t(`faq.${section.id}.q${n}`)}</summary>
                  <div className="faq-answer">
                    <Trans
                      i18nKey={aKey}
                      components={{
                        c1: <code />,
                        c2: <code />,
                        c3: <code />,
                        strong: <strong />,
                      }}
                    />
                  </div>
                </details>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
