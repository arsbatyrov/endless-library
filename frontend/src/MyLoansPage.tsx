import { useEffect, useState } from "react";

import { getBooks, getReader, getReaderLoans, loadErrorMsg } from "./api";
import { useSession } from "./auth";
import { formatDate, isOverdue } from "./format";
import { type Msg, useI18n } from "./i18n";
import type { Book, Loan, Reader } from "./types";

// Собственная карточка читателя (имя и email). Грузится отдельно от выдач: сбой одного не прячет другое.
type CardState =
  | { status: "loading" }
  | { status: "error"; message: Msg }
  | { status: "ready"; reader: Reader };

type State =
  | { status: "loading" }
  | { status: "error"; message: Msg }
  | { status: "ready"; loans: Loan[]; books: Book[] };

/** «Выдачи» для читателя: только его собственные книги на руках, без выдачи и возврата (это делает библиотекарь). */
export function MyLoansPage() {
  const { t, show, locale } = useI18n();
  const session = useSession();
  const readerId = session.status === "authenticated" ? session.user.reader_id : null;
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [card, setCard] = useState<CardState>({ status: "loading" });
  const [cardAttempt, setCardAttempt] = useState(0);

  useEffect(() => {
    if (readerId === null) {
      return;
    }
    const controller = new AbortController();
    getReader(readerId, controller.signal)
      .then((reader) => setCard({ status: "ready", reader }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setCard({ status: "error", message: loadErrorMsg(error) });
      });
    return () => controller.abort();
  }, [readerId, cardAttempt]);

  useEffect(() => {
    if (readerId === null) {
      return;
    }
    const controller = new AbortController();
    setState((previous) => (previous.status === "ready" ? previous : { status: "loading" }));
    Promise.all([getReaderLoans(readerId, controller.signal), getBooks(controller.signal)])
      .then(([loans, books]) => setState({ status: "ready", loans, books }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({ status: "error", message: loadErrorMsg(error) });
      });
    return () => controller.abort();
  }, [readerId, attempt]);

  if (readerId === null) {
    return (
      <section>
        <h2>{t("loans.heading")}</h2>
        <p role="alert" data-testid="my-loans-no-card">
          {t("loans.noCard")}
        </p>
      </section>
    );
  }

  function renderBody() {
    if (state.status === "loading") {
      return <p data-testid="my-loans-loading">{t("common.loading")}</p>;
    }
    if (state.status === "error") {
      return (
        <div role="alert" data-testid="my-loans-error">
          <p>{t("loans.listError", { message: show(state.message) })}</p>
          <button type="button" data-testid="my-loans-retry" onClick={() => setAttempt((n) => n + 1)}>
            {t("common.retry")}
          </button>
        </div>
      );
    }
    if (state.loans.length === 0) {
      return <p data-testid="my-loans-empty">{t("loans.mineEmpty")}</p>;
    }
    const title = (id: number) => state.books.find((book) => book.id === id)?.title ?? t("loans.unknownBook", { id });
    return (
      <table data-testid="loans-table">
        <thead>
          <tr>
            <th>{t("loans.col.book")}</th>
            <th>{t("loans.col.issued")}</th>
            <th>{t("loans.col.due")}</th>
          </tr>
        </thead>
        <tbody>
          {state.loans.map((loan) => (
            <tr key={loan.id} data-testid="loan-row">
              <td data-testid="loan-book">{title(loan.book_id)}</td>
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
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  function renderCard() {
    return (
      <section className="my-card" data-testid="my-card" aria-labelledby="my-card-heading">
        <h3 id="my-card-heading">{t("myCard.heading")}</h3>
        {card.status === "loading" && <p data-testid="my-card-loading">{t("common.loading")}</p>}
        {card.status === "error" && (
          <div role="alert" data-testid="my-card-error">
            <p>{t("myCard.loadError", { message: show(card.message) })}</p>
            <button type="button" data-testid="my-card-retry" onClick={() => setCardAttempt((n) => n + 1)}>
              {t("common.retry")}
            </button>
          </div>
        )}
        {card.status === "ready" && (
          <dl>
            <dt>{t("readers.col.name")}</dt>
            <dd data-testid="my-card-name">{card.reader.name}</dd>
            <dt>{t("readers.col.email")}</dt>
            <dd data-testid="my-card-email">{card.reader.email}</dd>
          </dl>
        )}
      </section>
    );
  }

  return (
    <section>
      <h2>{t("loans.heading")}</h2>
      {renderCard()}
      {renderBody()}
    </section>
  );
}
