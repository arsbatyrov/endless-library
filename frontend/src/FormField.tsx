import { useId } from "react";

interface Props {
  /** Имя поля в запросе к API: по нему показываем ошибку сервера именно под этим полем. */
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Сообщение сервера об ошибке в этом поле. */
  error?: string;
  type?: string;
  /** Префикс для data-testid: "book-form" даёт "book-form-title" и "book-form-error-title". */
  testIdPrefix: string;
}

/** Поле формы с подписью (label связана с input через id) и ошибкой под ним. */
export function FormField({ name, label, value, onChange, error, type = "text", testIdPrefix }: Props) {
  const inputId = useId();
  const errorId = `${inputId}-error`;

  return (
    <div className="field">
      <label htmlFor={inputId}>{label}</label>
      <input
        id={inputId}
        type={type}
        value={value}
        data-testid={`${testIdPrefix}-${name}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {error && (
        <p id={errorId} className="field-error" data-testid={`${testIdPrefix}-error-${name}`}>
          {error}
        </p>
      )}
    </div>
  );
}
