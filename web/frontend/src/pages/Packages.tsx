import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  downloadSkillBundle,
  listPackages,
  PackagePublishConflictError,
  platformPackageId,
  setPackagePublished,
  uploadSkillBundle,
  type PlatformPackageRow,
} from "../api/client";
import { EmptyState } from "../components/ds/EmptyState";
import { PageHeader } from "../components/ds/PageHeader";

function formatTime(iso: string | undefined): string {
  if (!iso) return "—";
  const d = Date.parse(iso);
  if (Number.isNaN(d)) return iso;
  return new Date(d).toLocaleString();
}

function validationSummary(row: PlatformPackageRow, t: (k: string) => string): string {
  if (typeof row.validation_passed === "boolean") {
    return row.validation_passed ? t("packages.validationOk") : t("packages.validationFail");
  }
  const fr = row.failure_reasons;
  if (Array.isArray(fr) && fr.length > 0) return fr.map(String).join("; ");
  if (typeof fr === "string" && fr.trim()) return fr.trim();
  return "—";
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function Packages() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<PlatformPackageRow[] | null>(null);
  const [listErr, setListErr] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);

  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [publishingId, setPublishingId] = useState<string | null>(null);
  const [conflictById, setConflictById] = useState<Record<string, string>>({});

  const [file, setFile] = useState<File | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);

  const loadList = useCallback(async () => {
    setListLoading(true);
    setListErr(null);
    try {
      const list = await listPackages();
      setRows(list);
    } catch (e) {
      setListErr(e instanceof Error ? e.message : String(e));
      setRows([]);
      toast.error(t("toast.networkError"));
    } finally {
      setListLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  async function onDownload(id: string) {
    setDownloadingId(id);
    setConflictById((c) => {
      const next = { ...c };
      delete next[id];
      return next;
    });
    try {
      const { blob, filename } = await downloadSkillBundle(id);
      triggerBlobDownload(blob, filename);
      toast.success(t("packages.downloadStarted"));
    } catch (e) {
      toast.error(t("toast.networkError"));
      const m = e instanceof Error ? e.message : String(e);
      setListErr(m);
    } finally {
      setDownloadingId(null);
    }
  }

  async function onTogglePublish(id: string, nextPublished: boolean) {
    setPublishingId(id);
    setConflictById((c) => {
      const next = { ...c };
      delete next[id];
      return next;
    });
    try {
      await setPackagePublished(id, nextPublished);
      toast.success(nextPublished ? t("packages.publishedOk") : t("packages.unpublishedOk"));
      void loadList();
    } catch (e) {
      if (e instanceof PackagePublishConflictError) {
        setConflictById((c) => ({ ...c, [id]: e.message }));
        toast.error(t("packages.publishConflictToast"));
      } else {
        toast.error(t("toast.networkError"));
        const m = e instanceof Error ? e.message : String(e);
        setListErr(m);
      }
    } finally {
      setPublishingId(null);
    }
  }

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      toast.error(t("packages.errNoFile"));
      return;
    }
    const name = file.name.toLowerCase();
    if (!name.endsWith(".tar.gz") && !name.endsWith(".tgz")) {
      toast.error(t("packages.errNotGzip"));
      return;
    }
    setUploadBusy(true);
    try {
      await uploadSkillBundle(file);
      toast.success(t("packages.uploadOk"));
      setFile(null);
      void loadList();
    } catch (err) {
      toast.error(t("toast.networkError"));
      setListErr(err instanceof Error ? err.message : String(err));
    } finally {
      setUploadBusy(false);
    }
  }

  return (
    <div className="packages-page">
      <PageHeader
        title={t("packages.title")}
        description={
          <Trans
            i18nKey="packages.lead"
            components={{
              strong: <strong />,
              c1: <code />,
              c2: <code />,
              c3: <code />,
            }}
          />
        }
        action={
          <button
            type="button"
            className="secondary"
            onClick={() => void loadList()}
            disabled={listLoading}
            aria-busy={listLoading}
          >
            {t("packages.refreshList")}
          </button>
        }
      />

      {listErr ? (
        <p className="warn-banner" role="alert">
          {listErr}
        </p>
      ) : null}

      <section className="panel packages-section" aria-labelledby="packages-upload-heading">
        <h2 id="packages-upload-heading" className="packages-section-title">
          {t("packages.sectionUpload")}
        </h2>
        <p className="muted packages-section-lead">{t("packages.sectionUploadLead")}</p>
        <form className="packages-form" onSubmit={onUpload}>
          <label className="packages-label">
            {t("packages.fileLabel")}
            <input
              type="file"
              accept=".tar.gz,.tgz,application/gzip"
              className="packages-file"
              onChange={(ev) => setFile(ev.target.files?.[0] ?? null)}
            />
          </label>
          <button type="submit" className="primary" disabled={uploadBusy} aria-busy={uploadBusy}>
            {t("packages.uploadSubmit")}
          </button>
        </form>
      </section>

      <section className="packages-list-wrap" aria-labelledby="packages-list-heading">
        <div className="packages-list-header">
          <h2 id="packages-list-heading" className="packages-section-title">
            {t("packages.sectionList")}
          </h2>
        </div>

        {listLoading && rows === null ? (
          <p className="muted">{t("packages.loadingList")}</p>
        ) : null}

        {!listLoading && rows && rows.length === 0 ? (
          <EmptyState title={t("packages.emptyTitle")} description={t("packages.emptyDesc")} />
        ) : null}

        {rows && rows.length > 0 ? (
          <div className="table-wrap">
            <table className="jobs-table packages-table">
              <thead>
                <tr>
                  <th scope="col">{t("packages.colId")}</th>
                  <th scope="col">{t("packages.colLabel")}</th>
                  <th scope="col">{t("packages.colPublished")}</th>
                  <th scope="col">{t("packages.colCreated")}</th>
                  <th scope="col">{t("packages.colValidation")}</th>
                  <th scope="col">{t("packages.colActions")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.filter((row) => platformPackageId(row)).map((row) => {
                  const id = platformPackageId(row);
                  const published = Boolean(row.published);
                  const label =
                    typeof row.label === "string" && row.label.trim() ? row.label.trim() : "—";
                  const conflict = conflictById[id];
                  return (
                    <tr key={id}>
                      <td>
                        <code>{id}</code>
                      </td>
                      <td>{label}</td>
                      <td>{published ? t("packages.yes") : t("packages.no")}</td>
                      <td>{formatTime(typeof row.created_at === "string" ? row.created_at : undefined)}</td>
                      <td className="packages-cell-validation">
                        {validationSummary(row, t)}
                      </td>
                      <td>
                        <div className="packages-actions">
                          <button
                            type="button"
                            className="secondary"
                            disabled={downloadingId === id}
                            aria-busy={downloadingId === id}
                            onClick={() => void onDownload(id)}
                          >
                            {t("packages.download")}
                          </button>
                          <button
                            type="button"
                            className={published ? "secondary" : "primary"}
                            disabled={publishingId === id}
                            aria-busy={publishingId === id}
                            onClick={() => void onTogglePublish(id, !published)}
                          >
                            {published ? t("packages.unpublish") : t("packages.publish")}
                          </button>
                        </div>
                        {conflict ? (
                          <pre className="packages-conflict" role="alert">
                            {conflict}
                          </pre>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        <p className="muted packages-jobs-hint">
          <Trans
            i18nKey="packages.jobsHint"
            components={{
              l1: <Link to="/jobs" />,
            }}
          />
        </p>
      </section>
    </div>
  );
}
