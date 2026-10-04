import { useEffect, useState } from "react";

import { getPopularBooks } from "./api";
import { useI18n } from "./i18n";
import type { PopularBook } from "./types";

type State =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: PopularBook[] };

/** Рейтинг самых выдаваемых книг. Ошибка здесь не должна ломать страницу: показываем короткое сообщение. */
export function PopularBooks({ refreshKey }: { refreshKey: number }) {
  const { t } = useI18n();
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
      <h3 id="popular-heading">{t("popular.heading")}</h3>
      {state.status === "loading" && <p data-testid="popular-loading">{t("common.loading")}</p>}
      {state.status === "error" && <p data-testid="popular-error">{t("popular.error")}</p>}
      {state.status === "ready" && state.items.length === 0 && (
        <p data-testid="popular-empty">{t("popular.empty")}</p>
      )}
      {state.status === "ready" && state.items.length > 0 && (
        <ol>
          {state.items.map(({ book, loans }) => (
            <li key={book.id} data-testid="popular-item">
              <span data-testid="popular-title">{book.title}</span>, {book.author}:{" "}
              <span data-testid="popular-loans">{loans}</span> {t("popular.loans")}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
