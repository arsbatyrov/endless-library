import { type FormEvent, useState } from "react";

import { ApiError, createBook, updateBook } from "./api";
import { FormField } from "./FormField";
import { msg, useI18n } from "./i18n";
import type { Book, BookInput, FormError } from "./types";

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
  const { t, show } = useI18n();
  const [title, setTitle] = useState(book?.title ?? "");
  const [author, setAuthor] = useState(book?.author ?? "");
  const [year, setYear] = useState(book?.year?.toString() ?? "");
  const [copies, setCopies] = useState(book?.copies_available.toString() ?? "1");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<FormError | null>(null);

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
      setError(
        caught instanceof ApiError
          ? { display: caught.display, fieldErrors: caught.fieldErrors }
          : { display: msg("common.networkError"), fieldErrors: {} },
      );
    } finally {
      setSubmitting(false);
    }
  }

  const errors = error?.fieldErrors ?? {};

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      data-testid="book-form"
      aria-label={book ? t("bookForm.editAria") : t("bookForm.new")}
    >
      <h3>{book ? t("bookForm.edit") : t("bookForm.new")}</h3>

      {error && (
        <p role="alert" className="form-error" data-testid="book-form-error">
          {show(error.display)}
        </p>
      )}

      <FormField testIdPrefix="book-form" name="title" label={t("bookForm.title")} value={title} onChange={setTitle} error={errors.title} />
      <FormField testIdPrefix="book-form" name="author" label={t("bookForm.author")} value={author} onChange={setAuthor} error={errors.author} />
      <FormField
        testIdPrefix="book-form"
        name="year"
        label={t("bookForm.year")}
        type="number"
        value={year}
        onChange={setYear}
        error={errors.year}
      />
      <FormField
        testIdPrefix="book-form"
        name="copies_available"
        label={t("bookForm.copies")}
        type="number"
        value={copies}
        onChange={setCopies}
        error={errors.copies_available}
      />

      <div className="actions">
        <button type="submit" disabled={submitting} data-testid="book-form-submit">
          {t("common.save")}
        </button>
        <button type="button" onClick={onCancel} data-testid="book-form-cancel">
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}
