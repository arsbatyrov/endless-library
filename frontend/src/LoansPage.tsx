import { useEffect, useState } from "react";

import {
  actionErrorMsg,
  getBooks,
  getReaderLoans,
  getReaders,
  issueBook,
  loadErrorMsg,
  returnBook,
} from "./api";
import { formatDate, isOverdue } from "./format";
import { type Msg, msg, useI18n } from "./i18n";
import type { Book, Loan, Reader } from "./types";

// Справочники (читатели и книги) для выпадающих списков.
type Catalog =
  | { status: "loading" }
  | { status: "error"; message: Msg }
  | { status: "ready"; readers: Reader[]; books: Book[] };

// Книги на руках у выбранного читателя.
type LoansState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: Msg }
  | { status: "ready"; loans: Loan[] };

export function LoansPage() {
  const { t, show, locale } = useI18n();
  const [catalog, setCatalog] = useState<Catalog>({ status: "loading" });
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [readerId, setReaderId] = useState<number | null>(null);
  const [loansState, setLoansState] = useState<LoansState>({ status: "idle" });
  const [loansAttempt, setLoansAttempt] = useState(0);
  const [bookId, setBookId] = useState("");
  // Сообщения хранятся как описания (ключ перевода + значения): при смене языка они переводятся сами.
  // Дату в описании храним как ISO-строку и форматируем при показе: формат даты зависит от языка.
  const [notice, setNotice] = useState<Msg | null>(null);
  const [actionError, setActionError] = useState<Msg | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setCatalog((previous) => (previous.status === "ready" ? previous : { status: "loading" }));

    Promise.all([getReaders(controller.signal), getBooks(controller.signal)])
      .then(([readers, books]) => setCatalog({ status: "ready", readers, books }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setCatalog({ status: "error", message: loadErrorMsg(error) });
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
        setLoansState({ status: "error", message: loadErrorMsg(error) });
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
        <h2>{t("loans.heading")}</h2>
        <p data-testid="loans-loading">{t("common.loading")}</p>
      </section>
    );
  }

  if (catalog.status === "error") {
    return (
      <section>
        <h2>{t("loans.heading")}</h2>
        <div role="alert" data-testid="loans-error">
          <p>{t("loans.loadError", { message: show(catalog.message) })}</p>
          <button type="button" data-testid="loans-retry" onClick={() => setCatalogAttempt((n) => n + 1)}>
            {t("common.retry")}
          </button>
        </div>
      </section>
    );
  }

  const { readers, books } = catalog;
  const bookTitle = (id: number) =>
    books.find((book) => book.id === id)?.title ?? t("loans.unknownBook", { id });

  // Сообщение о выдаче показывается с датой в формате текущего языка, поэтому показ делаем здесь,
  // а в состоянии храним только данные (название и ISO-дата).
  function renderNotice(message: Msg): string {
    if ("key" in message && message.key === "loans.issued" && message.params) {
      return t("loans.issued", {
        title: message.params.title,
        date: formatDate(String(message.params.dueIso), locale),
      });
    }
    return show(message);
  }

  async function handleIssue() {
    if (readerId === null || bookId === "") {
      return;
    }
    setNotice(null);
    setActionError(null);
    try {
      const loan = await issueBook(Number(bookId), readerId);
      setNotice(msg("loans.issued", { title: bookTitle(loan.book_id), dueIso: loan.due_at }));
      setBookId("");
    } catch (error) {
      setActionError(actionErrorMsg(error));
    }
    reloadAll();
  }

  async function handleReturn(loan: Loan) {
    setNotice(null);
    setActionError(null);
    try {
      const returned = await returnBook(loan.id);
      setNotice(msg("loans.returned", { title: bookTitle(loan.book_id), fine: returned.fine }));
    } catch (error) {
      setActionError(actionErrorMsg(error));
    }
    reloadAll();
  }

  function renderLoans() {
    if (loansState.status === "idle") {
      return <p data-testid="loans-pick-reader">{t("loans.pickReader")}</p>;
    }
    if (loansState.status === "loading") {
      return <p data-testid="loans-list-loading">{t("common.loading")}</p>;
    }
    if (loansState.status === "error") {
      return (
        <div role="alert" data-testid="loans-list-error">
          <p>{t("loans.listError", { message: show(loansState.message) })}</p>
          <button type="button" data-testid="loans-list-retry" onClick={() => setLoansAttempt((n) => n + 1)}>
            {t("common.retry")}
          </button>
        </div>
      );
    }
    if (loansState.loans.length === 0) {
      return <p data-testid="loans-empty">{t("loans.empty")}</p>;
    }
    return (
      <table data-testid="loans-table">
        <thead>
          <tr>
            <th>{t("loans.col.book")}</th>
            <th>{t("loans.col.issued")}</th>
            <th>{t("loans.col.due")}</th>
            <th>{t("common.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {loansState.loans.map((loan) => (
            <tr key={loan.id} data-testid="loan-row">
              <td data-testid="loan-book">{bookTitle(loan.book_id)}</td>
              <td data-testid="loan-issued">{formatDate(loan.issued_at, locale)}</td>
              <td data-testid="loan-due">
                {formatDate(loan.due_at, locale)}
                {isOverdue(loan.due_at) && (
                  <strong className="overdue" data-testid="loan-overdue">
                    {" "}
                    {t("loans.overdue")}
                  </strong>
                )}
              </td>
              <td>
                <button
                  type="button"
                  data-testid="loan-return"
                  aria-label={t("loans.returnAria", { title: bookTitle(loan.book_id) })}
                  onClick={() => handleReturn(loan)}
                >
                  {t("loans.return")}
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
      <h2>{t("loans.heading")}</h2>

      <div className="field">
        <label htmlFor="loans-reader">{t("loans.readerLabel")}</label>
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
          <option value="">{t("loans.chooseReader")}</option>
          {readers.map((reader) => (
            <option key={reader.id} value={reader.id}>
              {reader.name} ({reader.email})
            </option>
          ))}
        </select>
      </div>

      {notice && (
        <p role="status" className="notice" data-testid="loans-notice">
          {renderNotice(notice)}
        </p>
      )}
      {actionError && (
        <p role="alert" className="form-error" data-testid="loans-action-error">
          {show(actionError)}
        </p>
      )}

      {renderLoans()}

      {readerId !== null && (
        <form
          noValidate
          aria-label={t("loans.issueHeading")}
          data-testid="loan-form"
          onSubmit={(event) => {
            event.preventDefault();
            handleIssue();
          }}
        >
          <h3>{t("loans.issueHeading")}</h3>
          <div className="field">
            <label htmlFor="loans-book">{t("loans.bookLabel")}</label>
            <select
              id="loans-book"
              data-testid="loans-book"
              value={bookId}
              onChange={(event) => setBookId(event.target.value)}
            >
              <option value="">{t("loans.chooseBook")}</option>
              {books.map((book) => (
                <option key={book.id} value={book.id}>
                  {t("loans.bookOption", {
                    title: book.title,
                    author: book.author,
                    copies: book.copies_available,
                  })}
                </option>
              ))}
            </select>
          </div>
          <div className="actions">
            <button type="submit" disabled={bookId === ""} data-testid="loans-issue">
              {t("loans.issue")}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
