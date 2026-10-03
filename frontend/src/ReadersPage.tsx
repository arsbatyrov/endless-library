import { useEffect, useState } from "react";

import { ApiError, deleteReader, getReaders } from "./api";
import { ReaderForm } from "./ReaderForm";
import type { Reader } from "./types";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; readers: Reader[] };

type FormMode = { kind: "closed" } | { kind: "create" } | { kind: "edit"; reader: Reader };

// Экран устроен так же, как экран книг (см. BooksPage): загрузка / ошибка / данные, форма и удаление с подтверждением.
export function ReadersPage() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState<FormMode>({ kind: "closed" });
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
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
        const message = error instanceof Error ? error.message : "Неизвестная ошибка";
        setState({ status: "error", message });
      });

    return () => controller.abort();
  }, [attempt]);

  function handleSaved(saved: Reader) {
    setNotice(
      mode.kind === "edit" ? `Изменения читателя «${saved.name}» сохранены` : `Читатель «${saved.name}» добавлен`,
    );
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
      setNotice(`Читатель «${reader.name}» удалён`);
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : "Не удалось связаться с сервером");
    }
    reload();
  }

  function renderList() {
    if (state.status === "loading") {
      return <p data-testid="readers-loading">Загрузка…</p>;
    }

    if (state.status === "error") {
      return (
        <div role="alert" data-testid="readers-error">
          <p>Не удалось загрузить читателей: {state.message}</p>
          <button type="button" data-testid="readers-retry" onClick={reload}>
            Повторить
          </button>
        </div>
      );
    }

    if (state.readers.length === 0) {
      return <p data-testid="readers-empty">Пока нет ни одного читателя</p>;
    }

    return (
      <table data-testid="readers-table">
        <thead>
          <tr>
            <th>Имя</th>
            <th>Email</th>
            <th>Действия</th>
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
                    <span>Удалить «{reader.name}»?</span>
                    <button type="button" data-testid="reader-delete-confirm" onClick={() => handleDelete(reader)}>
                      Да, удалить
                    </button>
                    <button type="button" data-testid="reader-delete-cancel" onClick={() => setConfirmingId(null)}>
                      Отмена
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      data-testid="reader-edit"
                      aria-label={`Изменить «${reader.name}»`}
                      onClick={() => {
                        setNotice(null);
                        setActionError(null);
                        setMode({ kind: "edit", reader });
                      }}
                    >
                      Изменить
                    </button>
                    <button
                      type="button"
                      data-testid="reader-delete"
                      aria-label={`Удалить «${reader.name}»`}
                      onClick={() => {
                        setNotice(null);
                        setActionError(null);
                        setConfirmingId(reader.id);
                      }}
                    >
                      Удалить
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
      <h2>Читатели</h2>

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
          Добавить читателя
        </button>
      </div>

      {notice && (
        <p role="status" className="notice" data-testid="readers-notice">
          {notice}
        </p>
      )}
      {actionError && (
        <p role="alert" className="form-error" data-testid="readers-action-error">
          {actionError}
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
