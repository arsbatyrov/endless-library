import { useEffect, useState } from "react";

import { actionErrorMsg, deleteBook, getBooks, loadErrorMsg } from "./api";
import { useSession } from "./auth";
import { BookForm } from "./BookForm";
import { type Msg, msg, useI18n } from "./i18n";
import { PopularBooks } from "./PopularBooks";
import { canChangeCatalog } from "./roles";
import type { Book } from "./types";

// Загрузка списка: ровно одно из трёх состояний.
type State =
  | { status: "loading" }
  | { status: "error"; message: Msg }
  | { status: "ready"; books: Book[] };

// Форма закрыта, открыта для новой книги или для изменения существующей.
type FormMode = { kind: "closed" } | { kind: "create" } | { kind: "edit"; book: Book };

export function BooksPage() {
  // t и show зависят от выбранного языка; useI18n перерисовывает компонент при его смене.
  const { t, show } = useI18n();
  const session = useSession();
  // Читатель только читает каталог: кнопок добавления, изменения и удаления у него нет (сервер всё равно ответил бы 403).
  const canChange = session.status === "authenticated" && canChangeCatalog(session.user.role);
  const [state, setState] = useState<State>({ status: "loading" });
  // Увеличиваем число, чтобы перечитать список (после действий и по кнопке «Повторить»).
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState<FormMode>({ kind: "closed" });
  // Сообщения хранятся как описания (ключ перевода + значения), а не как готовый текст:
  // так при смене языка уже показанное сообщение тоже переводится.
  const [notice, setNotice] = useState<Msg | null>(null);
  const [actionError, setActionError] = useState<Msg | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);

  const reload = () => setAttempt((n) => n + 1);

  useEffect(() => {
    // AbortController отменяет запрос, если компонент убрали с экрана раньше ответа.
    const controller = new AbortController();
    // При повторном чтении оставляем на экране прежний список, а не мигаем «Загрузкой».
    setState((previous) => (previous.status === "ready" ? previous : { status: "loading" }));

    getBooks(controller.signal)
      .then((books) => setState({ status: "ready", books }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({ status: "error", message: loadErrorMsg(error) });
      });

    return () => controller.abort();
  }, [attempt]);

  function handleSaved(saved: Book) {
    setNotice(msg(mode.kind === "edit" ? "books.saved" : "books.added", { title: saved.title }));
    setActionError(null);
    setMode({ kind: "closed" });
    reload();
  }

  async function handleDelete(book: Book) {
    setConfirmingId(null);
    setNotice(null);
    setActionError(null);
    try {
      await deleteBook(book.id);
      setNotice(msg("books.deleted", { title: book.title }));
    } catch (error) {
      setActionError(actionErrorMsg(error));
    }
    // Перечитываем список в любом случае: например, книгу уже могли удалить в другой вкладке (404).
    reload();
  }

  function renderList() {
    if (state.status === "loading") {
      return <p data-testid="books-loading">{t("common.loading")}</p>;
    }

    if (state.status === "error") {
      return (
        <div role="alert" data-testid="books-error">
          <p>{t("books.loadError", { message: show(state.message) })}</p>
          <button type="button" data-testid="books-retry" onClick={reload}>
            {t("common.retry")}
          </button>
        </div>
      );
    }

    if (state.books.length === 0) {
      return <p data-testid="books-empty">{t("books.empty")}</p>;
    }

    return (
      <table data-testid="books-table">
        <thead>
          <tr>
            <th>{t("books.col.title")}</th>
            <th>{t("books.col.author")}</th>
            <th>{t("books.col.year")}</th>
            <th>{t("books.col.inStock")}</th>
            {canChange && <th>{t("common.actions")}</th>}
          </tr>
        </thead>
        <tbody>
          {state.books.map((book) => (
            <tr key={book.id} data-testid="book-row">
              <td data-testid="book-title">{book.title}</td>
              <td data-testid="book-author">{book.author}</td>
              <td data-testid="book-year">{book.year ?? "—"}</td>
              <td data-testid="book-copies">{book.copies_available}</td>
              {canChange && (
                <td className="row-actions">
                  {confirmingId === book.id ? (
                    <>
                      <span>{t("books.deleteQuestion", { title: book.title })}</span>
                      <button type="button" data-testid="book-delete-confirm" onClick={() => handleDelete(book)}>
                        {t("common.confirmDelete")}
                      </button>
                      <button type="button" data-testid="book-delete-cancel" onClick={() => setConfirmingId(null)}>
                        {t("common.cancel")}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        data-testid="book-edit"
                        aria-label={t("books.editAria", { title: book.title })}
                        onClick={() => {
                          setNotice(null);
                          setActionError(null);
                          setMode({ kind: "edit", book });
                        }}
                      >
                        {t("common.edit")}
                      </button>
                      <button
                        type="button"
                        data-testid="book-delete"
                        aria-label={t("books.deleteAria", { title: book.title })}
                        onClick={() => {
                          setNotice(null);
                          setActionError(null);
                          setConfirmingId(book.id);
                        }}
                      >
                        {t("common.delete")}
                      </button>
                    </>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <section>
      <h2>{t("books.heading")}</h2>

      {canChange && (
        <div className="toolbar">
          <button
            type="button"
            data-testid="books-add"
            disabled={mode.kind !== "closed"}
            onClick={() => {
              setNotice(null);
              setActionError(null);
              setMode({ kind: "create" });
            }}
          >
            {t("books.add")}
          </button>
        </div>
      )}

      {notice && (
        <p role="status" className="notice" data-testid="books-notice">
          {show(notice)}
        </p>
      )}
      {actionError && (
        <p role="alert" className="form-error" data-testid="books-action-error">
          {show(actionError)}
        </p>
      )}

      {canChange && mode.kind !== "closed" && (
        // key заставляет React создать форму заново при переходе между книгами (сброс введённых значений)
        <BookForm
          key={mode.kind === "edit" ? mode.book.id : "new"}
          book={mode.kind === "edit" ? mode.book : undefined}
          onSaved={handleSaved}
          onCancel={() => setMode({ kind: "closed" })}
        />
      )}

      {renderList()}

      <PopularBooks refreshKey={attempt} />
    </section>
  );
}
