import { useEffect, useState } from "react";

import { getBooks } from "./api";
import type { Book } from "./types";

// Экран может быть в одном из трёх состояний: загрузка, ошибка или данные.
type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; books: Book[] };

export function BooksPage() {
  const [state, setState] = useState<State>({ status: "loading" });
  // Увеличиваем число, чтобы повторить загрузку по кнопке «Повторить».
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // AbortController отменяет запрос, если компонент убрали с экрана раньше ответа.
    const controller = new AbortController();
    setState({ status: "loading" });

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

  // data-testid нужны автотестам: по ним они находят элементы, не завися от вёрстки и текста.
  if (state.status === "loading") {
    return <p data-testid="books-loading">Загрузка…</p>;
  }

  if (state.status === "error") {
    return (
      <div role="alert" data-testid="books-error">
        <p>Не удалось загрузить книги: {state.message}</p>
        <button type="button" data-testid="books-retry" onClick={() => setAttempt((n) => n + 1)}>
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
        </tr>
      </thead>
      <tbody>
        {state.books.map((book) => (
          <tr key={book.id} data-testid="book-row">
            <td data-testid="book-title">{book.title}</td>
            <td data-testid="book-author">{book.author}</td>
            <td data-testid="book-year">{book.year ?? "—"}</td>
            <td data-testid="book-copies">{book.copies_available}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
