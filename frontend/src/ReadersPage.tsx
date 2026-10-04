import { useEffect, useState } from "react";

import { actionErrorMsg, deleteReader, getReaders, loadErrorMsg } from "./api";
import { type Msg, msg, useI18n } from "./i18n";
import { ReaderForm } from "./ReaderForm";
import type { Reader } from "./types";

type State =
  | { status: "loading" }
  | { status: "error"; message: Msg }
  | { status: "ready"; readers: Reader[] };

type FormMode = { kind: "closed" } | { kind: "create" } | { kind: "edit"; reader: Reader };

// Экран устроен так же, как экран книг (см. BooksPage): загрузка / ошибка / данные, форма и удаление с подтверждением.
export function ReadersPage() {
  const { t, show } = useI18n();
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState<FormMode>({ kind: "closed" });
  const [notice, setNotice] = useState<Msg | null>(null);
  const [actionError, setActionError] = useState<Msg | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);

  const reload = () => setAttempt((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => (previous.status === "ready" ? previous : { status: "loading" }));

    getReaders(controller.signal)
      .then((readers) => setState({ status: "ready", readers }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({ status: "error", message: loadErrorMsg(error) });
      });

    return () => controller.abort();
  }, [attempt]);

  function handleSaved(saved: Reader) {
    setNotice(msg(mode.kind === "edit" ? "readers.saved" : "readers.added", { name: saved.name }));
    setActionError(null);
    setMode({ kind: "closed" });
    reload();
  }

  async function handleDelete(reader: Reader) {
    setConfirmingId(null);
    setNotice(null);
    setActionError(null);
    try {
      await deleteReader(reader.id);
      setNotice(msg("readers.deleted", { name: reader.name }));
    } catch (error) {
      setActionError(actionErrorMsg(error));
    }
    reload();
  }

  function renderList() {
    if (state.status === "loading") {
      return <p data-testid="readers-loading">{t("common.loading")}</p>;
    }

    if (state.status === "error") {
      return (
        <div role="alert" data-testid="readers-error">
          <p>{t("readers.loadError", { message: show(state.message) })}</p>
          <button type="button" data-testid="readers-retry" onClick={reload}>
            {t("common.retry")}
          </button>
        </div>
      );
    }

    if (state.readers.length === 0) {
      return <p data-testid="readers-empty">{t("readers.empty")}</p>;
    }

    return (
      <table data-testid="readers-table">
        <thead>
          <tr>
            <th>{t("readers.col.name")}</th>
            <th>{t("readers.col.email")}</th>
            <th>{t("common.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {state.readers.map((reader) => (
            <tr key={reader.id} data-testid="reader-row">
              <td data-testid="reader-name">{reader.name}</td>
              <td data-testid="reader-email">{reader.email}</td>
              <td className="row-actions">
                {confirmingId === reader.id ? (
                  <>
                    <span>{t("readers.deleteQuestion", { name: reader.name })}</span>
                    <button type="button" data-testid="reader-delete-confirm" onClick={() => handleDelete(reader)}>
                      {t("common.confirmDelete")}
                    </button>
                    <button type="button" data-testid="reader-delete-cancel" onClick={() => setConfirmingId(null)}>
                      {t("common.cancel")}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      data-testid="reader-edit"
                      aria-label={t("readers.editAria", { name: reader.name })}
                      onClick={() => {
                        setNotice(null);
                        setActionError(null);
                        setMode({ kind: "edit", reader });
                      }}
                    >
                      {t("common.edit")}
                    </button>
                    <button
                      type="button"
                      data-testid="reader-delete"
                      aria-label={t("readers.deleteAria", { name: reader.name })}
                      onClick={() => {
                        setNotice(null);
                        setActionError(null);
                        setConfirmingId(reader.id);
                      }}
                    >
                      {t("common.delete")}
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <section>
      <h2>{t("readers.heading")}</h2>

      <div className="toolbar">
        <button
          type="button"
          data-testid="readers-add"
          disabled={mode.kind !== "closed"}
          onClick={() => {
            setNotice(null);
            setActionError(null);
            setMode({ kind: "create" });
          }}
        >
          {t("readers.add")}
        </button>
      </div>

      {notice && (
        <p role="status" className="notice" data-testid="readers-notice">
          {show(notice)}
        </p>
      )}
      {actionError && (
        <p role="alert" className="form-error" data-testid="readers-action-error">
          {show(actionError)}
        </p>
      )}

      {mode.kind !== "closed" && (
        <ReaderForm
          key={mode.kind === "edit" ? mode.reader.id : "new"}
          reader={mode.kind === "edit" ? mode.reader : undefined}
          onSaved={handleSaved}
          onCancel={() => setMode({ kind: "closed" })}
        />
      )}

      {renderList()}
    </section>
  );
}
