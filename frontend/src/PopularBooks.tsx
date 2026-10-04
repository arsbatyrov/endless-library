import { useEffect, useState } from "react";

import { getPopularBooks } from "./api";
import type { PopularBook } from "./types";

type State =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: PopularBook[] };

/** Рейтинг самых выдаваемых книг. Ошибка здесь не должна ломать страницу: показываем короткое сообщение. */
export function PopularBooks({ refreshKey }: { refreshKey: number }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getPopularBooks(5, controller.signal)
      .then((items) => setState({ status: "ready", items }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({ status: "error" });
      });
    return () => controller.abort();
  }, [refreshKey]);

  return (
    <section className="popular" data-testid="popular" aria-labelledby="popular-heading">
      <h3 id="popular-heading">Популярные книги</h3>
      {state.status === "loading" && <p data-testid="popular-loading">Загрузка…</p>}
      {state.status === "error" && (
        <p data-testid="popular-error">Рейтинг временно недоступен</p>
      )}
      {state.status === "ready" && state.items.length === 0 && (
        <p data-testid="popular-empty">Книги пока не выдавали</p>
      )}
      {state.status === "ready" && state.items.length > 0 && (
        <ol>
          {state.items.map(({ book, loans }) => (
            <li key={book.id} data-testid="popular-item">
              <span data-testid="popular-title">{book.title}</span>, {book.author}:{" "}
              <span data-testid="popular-loans">{loans}</span> выдач
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
