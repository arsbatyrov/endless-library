import { useEffect, useState } from "react";

import { ApiError, deleteBook, getBooks } from "./api";
import { BookForm } from "./BookForm";
import type { Book } from "./types";

// Загрузка списка: ровно одно из трёх состояний.
type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; books: Book[] };

// Форма закрыта, открыта для новой книги или для изменения существующей.
type FormMode = { kind: "closed" } | { kind: "create" } | { kind: "edit"; book: Book };

export function BooksPage() {
  const [state, setState] = useState<State>({ status: "loading" });
  // Увеличиваем число, чтобы перечитать список (после действий и по кнопке «Повторить»).
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState<FormMode>({ kind: "closed" });
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
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
        const message = error instanceof Error ? error.message : "Неизвестная ошибка";
        setState({ status: "error", message });
      });

    return () => controller.abort();
  }, [attempt]);

  function handleSaved(saved: Book) {
    setNotice(mode.kind === "edit" ? `Изменения книги «${saved.title}» сохранены` : `Книга «${saved.title}» добавлена`);
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
      setNotice(`Книга «${book.title}» удалена`);
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : "Не удалось связаться с сервером");
    }
    // Перечитываем список в любом случае: например, книгу уже могли удалить в другой вкладке (404).
    reload();
  }

  function renderList() {
    if (state.status === "loading") {
      return <p data-testid="books-loading">Загрузка…</p>;
    }

    if (state.status === "error") {
      return (
        <div role="alert" data-testid="books-error">
          <p>Не удалось загрузить книги: {state.message}</p>
          <button type="button" data-testid="books-retry" onClick={reload}>
            Повторить
          </button>
        </div>
      );
    }

    if (state.books.length === 0) {
      return <p data-testid="books-empty">Пока нет ни одной книги</p>;
    }

    return (
      <table data-testid="books-table">
        <thead>
          <tr>
            <th>Название</th>
            <th>Автор</th>
            <th>Год</th>
            <th>В наличии</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {state.books.map((book) => (
            <tr key={book.id} data-testid="book-row">
              <td data-testid="book-title">{book.title}</td>
              <td data-testid="book-author">{book.author}</td>
              <td data-testid="book-year">{book.year ?? "—"}</td>
              <td data-testid="book-copies">{book.copies_available}</td>
              <td className="row-actions">
                {confirmingId === book.id ? (
                  <>
                    <span>Удалить «{book.title}»?</span>
                    <button type="button" data-testid="book-delete-confirm" onClick={() => handleDelete(book)}>
                      Да, удалить
                    </button>
                    <button type="button" data-testid="book-delete-cancel" onClick={() => setConfirmingId(null)}>
                      Отмена
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      data-testid="book-edit"
                      aria-label={`Изменить «${book.title}»`}
                      onClick={() => {
                        setNotice(null);
                        setActionError(null);
                        setMode({ kind: "edit", book });
                      }}
                    >
                      Изменить
                    </button>
                    <button
                      type="button"
                      data-testid="book-delete"
                      aria-label={`Удалить «${book.title}»`}
                      onClick={() => {
                        setNotice(null);
                        setActionError(null);
                        setConfirmingId(book.id);
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
      <h2>Книги</h2>

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
          Добавить книгу
        </button>
      </div>

      {notice && (
        <p role="status" className="notice" data-testid="books-notice">
          {notice}
        </p>
      )}
      {actionError && (
        <p role="alert" className="form-error" data-testid="books-action-error">
          {actionError}
        </p>
      )}

      {mode.kind !== "closed" && (
        // key заставляет React создать форму заново при переходе между книгами (сброс введённых значений)
        <BookForm
          key={mode.kind === "edit" ? mode.book.id : "new"}
          book={mode.kind === "edit" ? mode.book : undefined}
          onSaved={handleSaved}
          onCancel={() => setMode({ kind: "closed" })}
        />
      )}

      {renderList()}
    </section>
  );
}
