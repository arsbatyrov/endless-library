import { type FormEvent, useState } from "react";

import { ApiError, createReader, updateReader } from "./api";
import { FormField } from "./FormField";
import type { FormError, Reader } from "./types";

interface Props {
  /** Если передан читатель, форма его изменяет, иначе создаёт нового. */
  reader?: Reader;
  onSaved: (reader: Reader) => void;
  onCancel: () => void;
}

export function ReaderForm({ reader, onSaved, onCancel }: Props) {
  const [name, setName] = useState(reader?.name ?? "");
  const [email, setEmail] = useState(reader?.email ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<FormError | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const input = { name, email };
      const saved = reader ? await updateReader(reader.id, input) : await createReader(input);
      onSaved(saved);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught : { message: "Не удалось связаться с сервером", fieldErrors: {} },
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
      data-testid="reader-form"
      aria-label={reader ? "Изменение читателя" : "Новый читатель"}
    >
      <h3>{reader ? "Изменить читателя" : "Новый читатель"}</h3>

      {error && (
        // Для 409 («email занят») здесь единственное сообщение, для 422 дополнительно есть ошибки по полям.
        <p role="alert" className="form-error" data-testid="reader-form-error">
          {error.message}
        </p>
      )}

      <FormField testIdPrefix="reader-form" name="name" label="Имя" value={name} onChange={setName} error={errors.name} />
      <FormField testIdPrefix="reader-form" name="email" label="Email" type="email" value={email} onChange={setEmail} error={errors.email} />

      <div className="actions">
        <button type="submit" disabled={submitting} data-testid="reader-form-submit">
          Сохранить
        </button>
        <button type="button" onClick={onCancel} data-testid="reader-form-cancel">
          Отмена
        </button>
      </div>
    </form>
  );
}
