import { type FormEvent, useId, useState } from "react";

import { ApiError, createBook, updateBook } from "./api";
import type { Book, BookInput } from "./types";

interface Props {
  /** Если передана книга, форма её изменяет, иначе создаёт новую. */
  book?: Book;
  onSaved: (book: Book) => void;
  onCancel: () => void;
}

/** Пустую строку превращаем в null, остальное в число: проверку значения делает сервер. */
function toNumber(text: string): number | null {
  return text.trim() === "" ? null : Number(text);
}

export function BookForm({ book, onSaved, onCancel }: Props) {
  const idPrefix = useId();
  const [title, setTitle] = useState(book?.title ?? "");
  const [author, setAuthor] = useState(book?.author ?? "");
  const [year, setYear] = useState(book?.year?.toString() ?? "");
  const [copies, setCopies] = useState(book?.copies_available.toString() ?? "1");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | { message: string; fieldErrors: Record<string, string> } | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const input: BookInput = {
      title,
      author,
      year: toNumber(year),
      copies_available: toNumber(copies),
    };

    try {
      const saved = book ? await updateBook(book.id, input) : await createBook(input);
      onSaved(saved);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught);
      } else {
        setError({ message: "Не удалось связаться с сервером", fieldErrors: {} });
      }
    } finally {
      setSubmitting(false);
    }
  }

  const fieldErrors = error?.fieldErrors ?? {};

  // Поле с подписью (label связана с input через id), а ошибка сервера выводится под ним.
  function field(name: string, label: string, value: string, set: (v: string) => void, type = "text") {
    const inputId = `${idPrefix}-${name}`;
    const errorId = `${inputId}-error`;
    const message = fieldErrors[name];
    return (
      <div className="field">
        <label htmlFor={inputId}>{label}</label>
        <input
          id={inputId}
          type={type}
          value={value}
          data-testid={`book-form-${name}`}
          aria-invalid={message ? true : undefined}
          aria-describedby={message ? errorId : undefined}
          onChange={(event) => set(event.target.value)}
        />
        {message && (
          <p id={errorId} className="field-error" data-testid={`book-form-error-${name}`}>
            {message}
          </p>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate data-testid="book-form" aria-label={book ? "Изменение книги" : "Новая книга"}>
      <h3>{book ? "Изменить книгу" : "Новая книга"}</h3>

      {error && (
        <p role="alert" className="form-error" data-testid="book-form-error">
          {error.message}
        </p>
      )}

      {field("title", "Название", title, setTitle)}
      {field("author", "Автор", author, setAuthor)}
      {field("year", "Год издания", year, setYear, "number")}
      {field("copies_available", "Количество экземпляров", copies, setCopies, "number")}

      <div className="actions">
        <button type="submit" disabled={submitting} data-testid="book-form-submit">
          Сохранить
        </button>
        <button type="button" onClick={onCancel} data-testid="book-form-cancel">
          Отмена
        </button>
      </div>
    </form>
  );
}
