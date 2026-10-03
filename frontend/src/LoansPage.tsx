import { useEffect, useState } from "react";

import { ApiError, getBooks, getReaderLoans, getReaders, issueBook, returnBook } from "./api";
import { formatDate, isOverdue } from "./format";
import type { Book, Loan, Reader } from "./types";

// Справочники (читатели и книги) для выпадающих списков.
type Catalog =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; readers: Reader[]; books: Book[] };

// Книги на руках у выбранного читателя.
type LoansState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; loans: Loan[] };

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Не удалось связаться с сервером";
}

export function LoansPage() {
  const [catalog, setCatalog] = useState<Catalog>({ status: "loading" });
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [readerId, setReaderId] = useState<number | null>(null);
  const [loansState, setLoansState] = useState<LoansState>({ status: "idle" });
  const [loansAttempt, setLoansAttempt] = useState(0);
  const [bookId, setBookId] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setCatalog((previous) => (previous.status === "ready" ? previous : { status: "loading" }));

    Promise.all([getReaders(controller.signal), getBooks(controller.signal)])
      .then(([readers, books]) => setCatalog({ status: "ready", readers, books }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setCatalog({ status: "error", message: error instanceof Error ? error.message : "Неизвестная ошибка" });
      });

    return () => controller.abort();
  }, [catalogAttempt]);

  useEffect(() => {
    if (readerId === null) {
      setLoansState({ status: "idle" });
      return;
    }
    const controller = new AbortController();
    setLoansState((previous) => (previous.status === "ready" ? previous : { status: "loading" }));

    getReaderLoans(readerId, controller.signal)
      .then((loans) => setLoansState({ status: "ready", loans }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setLoansState({ status: "error", message: error instanceof Error ? error.message : "Неизвестная ошибка" });
      });

    return () => controller.abort();
  }, [readerId, loansAttempt]);

  // После выдачи и возврата меняется и список на руках, и число экземпляров в списке книг.
  function reloadAll() {
    setLoansAttempt((n) => n + 1);
    setCatalogAttempt((n) => n + 1);
  }

  if (catalog.status === "loading") {
    return (
      <section>
        <h2>Выдачи</h2>
        <p data-testid="loans-loading">Загрузка…</p>
      </section>
    );
  }

  if (catalog.status === "error") {
    return (
      <section>
        <h2>Выдачи</h2>
        <div role="alert" data-testid="loans-error">
          <p>Не удалось загрузить данные: {catalog.message}</p>
          <button type="button" data-testid="loans-retry" onClick={() => setCatalogAttempt((n) => n + 1)}>
            Повторить
          </button>
        </div>
      </section>
    );
  }

  const { readers, books } = catalog;
  const bookTitle = (id: number) => books.find((book) => book.id === id)?.title ?? `книга №${id}`;

  async function handleIssue() {
    if (readerId === null || bookId === "") {
      return;
    }
    setNotice(null);
    setActionError(null);
    try {
      const loan = await issueBook(Number(bookId), readerId);
      setNotice(`Книга «${bookTitle(loan.book_id)}» выдана, вернуть до ${formatDate(loan.due_at)}`);
      setBookId("");
    } catch (error) {
      setActionError(errorMessage(error));
    }
    reloadAll();
  }

  async function handleReturn(loan: Loan) {
    setNotice(null);
    setActionError(null);
    try {
      const returned = await returnBook(loan.id);
      setNotice(`Книга «${bookTitle(loan.book_id)}» возвращена. Штраф: ${returned.fine}`);
    } catch (error) {
      setActionError(errorMessage(error));
    }
    reloadAll();
  }

  function renderLoans() {
    if (loansState.status === "idle") {
      return <p data-testid="loans-pick-reader">Выберите читателя, чтобы увидеть его книги и выдать новую</p>;
    }
    if (loansState.status === "loading") {
      return <p data-testid="loans-list-loading">Загрузка…</p>;
    }
    if (loansState.status === "error") {
      return (
        <div role="alert" data-testid="loans-list-error">
          <p>Не удалось загрузить выдачи: {loansState.message}</p>
          <button type="button" data-testid="loans-list-retry" onClick={() => setLoansAttempt((n) => n + 1)}>
            Повторить
          </button>
        </div>
      );
    }
    if (loansState.loans.length === 0) {
      return <p data-testid="loans-empty">У читателя нет книг на руках</p>;
    }
    return (
      <table data-testid="loans-table">
        <thead>
          <tr>
            <th>Книга</th>
            <th>Выдана</th>
            <th>Вернуть до</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {loansState.loans.map((loan) => (
            <tr key={loan.id} data-testid="loan-row">
              <td data-testid="loan-book">{bookTitle(loan.book_id)}</td>
              <td data-testid="loan-issued">{formatDate(loan.issued_at)}</td>
              <td data-testid="loan-due">
                {formatDate(loan.due_at)}
                {isOverdue(loan.due_at) && (
                  <strong className="overdue" data-testid="loan-overdue">
                    {" "}
                    просрочено
                  </strong>
                )}
              </td>
              <td>
                <button
                  type="button"
                  data-testid="loan-return"
                  aria-label={`Вернуть «${bookTitle(loan.book_id)}»`}
                  onClick={() => handleReturn(loan)}
                >
                  Вернуть
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <section>
      <h2>Выдачи</h2>

      <div className="field">
        <label htmlFor="loans-reader">Читатель</label>
        <select
          id="loans-reader"
          data-testid="loans-reader"
          value={readerId ?? ""}
          onChange={(event) => {
            setReaderId(event.target.value === "" ? null : Number(event.target.value));
            setBookId("");
            setNotice(null);
            setActionError(null);
          }}
        >
          <option value="">— выберите читателя —</option>
          {readers.map((reader) => (
            <option key={reader.id} value={reader.id}>
              {reader.name} ({reader.email})
            </option>
          ))}
        </select>
      </div>

      {notice && (
        <p role="status" className="notice" data-testid="loans-notice">
          {notice}
        </p>
      )}
      {actionError && (
        <p role="alert" className="form-error" data-testid="loans-action-error">
          {actionError}
        </p>
      )}

      {renderLoans()}

      {readerId !== null && (
        <form
          noValidate
          aria-label="Выдать книгу"
          data-testid="loan-form"
          onSubmit={(event) => {
            event.preventDefault();
            handleIssue();
          }}
        >
          <h3>Выдать книгу</h3>
          <div className="field">
            <label htmlFor="loans-book">Книга</label>
            <select
              id="loans-book"
              data-testid="loans-book"
              value={bookId}
              onChange={(event) => setBookId(event.target.value)}
            >
              <option value="">— выберите книгу —</option>
              {books.map((book) => (
                <option key={book.id} value={book.id}>
                  {book.title} — {book.author} (в наличии: {book.copies_available})
                </option>
              ))}
            </select>
          </div>
          <div className="actions">
            <button type="submit" disabled={bookId === ""} data-testid="loans-issue">
              Выдать
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
