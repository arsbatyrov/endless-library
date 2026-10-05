import { type FormEvent, useRef, useState } from "react";

import { ApiError } from "./apiError";
import { login } from "./auth";
import { FormField } from "./FormField";
import { type Msg, msg, useI18n } from "./i18n";

interface Props {
  /** Сеанс закончился сам (токен нельзя обновить): объясняем, почему показана страница входа. */
  expired: boolean;
}

/** Страница входа: единственное, что видит человек без входа. Данных библиотеки здесь нет. */
export function LoginPage({ expired }: Props) {
  const { t, show } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Msg | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
    } catch (caught) {
      // Сообщение сервера показываем как есть, без перевода (неверные данные, слишком много попыток).
      setError(caught instanceof ApiError ? caught.display : msg("common.networkError"));
      setSubmitting(false);
      // Поля не очищаем, фокус остаётся в форме: человек сразу может поправить пароль.
      passwordRef.current?.focus();
      passwordRef.current?.select();
    }
    // При успехе страница входа исчезает (App показывает разделы), поэтому состояние здесь не сбрасываем.
  }

  return (
    <form onSubmit={handleSubmit} data-testid="login-form" aria-label={t("auth.title")}>
      <h2>{t("auth.title")}</h2>
      <p>{t("auth.intro")}</p>

      {expired && (
        <p role="status" className="notice" data-testid="login-expired">
          {t("auth.sessionExpired")}
        </p>
      )}
      {error && (
        <p role="alert" className="form-error" data-testid="login-error">
          {show(error)}
        </p>
      )}

      <FormField
        testIdPrefix="login"
        name="username"
        label={t("auth.username")}
        value={username}
        onChange={setUsername}
        autoComplete="username"
      />
      <FormField
        testIdPrefix="login"
        name="password"
        label={t("auth.password")}
        type="password"
        value={password}
        onChange={setPassword}
        autoComplete="current-password"
        inputRef={passwordRef}
      />

      <div className="actions">
        <button type="submit" disabled={submitting} data-testid="login-submit">
          {submitting ? t("auth.submitting") : t("auth.submit")}
        </button>
      </div>
    </form>
  );
}
