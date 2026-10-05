import { type FormEvent, useId, useState } from "react";

import { actionErrorMsg, ApiError, resetAccountPassword, setAccountActive } from "./api";
import { type Msg, msg, useI18n } from "./i18n";
import type { Account } from "./types";

interface Props {
  account: Account;
  /** Действие выполнено: сообщение для показа над таблицей (страница потом перечитывает список). */
  onDone: (message: Msg) => void;
  /** Сервер отказал (например, это последний активный админ): сообщение сервера как есть. */
  onFailed: (message: Msg) => void;
}

type Mode = "idle" | "confirmDisable" | "reset";

/** Кнопки над учётной записью: отключить (с подтверждением), включить, сбросить пароль. */
export function AccountActions({ account, onDone, onFailed }: Props) {
  const { t } = useI18n();
  const [mode, setMode] = useState<Mode>("idle");
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const passwordId = useId();
  const params = { username: account.username };

  async function changeActive(active: boolean) {
    setBusy(true);
    setMode("idle");
    try {
      await setAccountActive(account.id, active);
      onDone(msg(active ? "users.enabledDone" : "users.disabledDone", params));
    } catch (error) {
      onFailed(actionErrorMsg(error));
    } finally {
      setBusy(false);
    }
  }

  async function handleReset(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setPasswordError(null);
    try {
      await resetAccountPassword(account.id, password);
      setMode("idle");
      setPassword("");
      onDone(msg("users.passwordResetDone", params));
    } catch (error) {
      if (error instanceof ApiError && error.fieldErrors.new_password) {
        // например «пароль короче 8 символов»: показываем под полем, форма остаётся открытой
        setPasswordError(error.fieldErrors.new_password);
      } else {
        setMode("idle");
        onFailed(actionErrorMsg(error));
      }
    } finally {
      setBusy(false);
    }
  }

  if (mode === "confirmDisable") {
    return (
      <>
        <span data-testid="user-disable-question">{t("users.disableQuestion", params)}</span>
        <button type="button" data-testid="user-disable-confirm" disabled={busy} onClick={() => changeActive(false)}>
          {t("users.disableConfirm")}
        </button>
        <button type="button" data-testid="user-disable-cancel" onClick={() => setMode("idle")}>
          {t("common.cancel")}
        </button>
      </>
    );
  }

  if (mode === "reset") {
    return (
      <form noValidate data-testid="user-reset-form" onSubmit={handleReset} aria-label={t("users.resetAria", params)}>
        <div className="field">
          <label htmlFor={passwordId}>{t("resetForm.label")}</label>
          <input
            id={passwordId}
            type="password"
            autoComplete="new-password"
            data-testid="user-reset-password"
            value={password}
            aria-invalid={passwordError ? true : undefined}
            onChange={(event) => setPassword(event.target.value)}
          />
          {passwordError && (
            <p className="field-error" data-testid="user-reset-error">
              {passwordError}
            </p>
          )}
        </div>
        <button type="submit" disabled={busy} data-testid="user-reset-submit">
          {t("resetForm.submit")}
        </button>
        <button
          type="button"
          data-testid="user-reset-cancel"
          onClick={() => {
            setMode("idle");
            setPassword("");
            setPasswordError(null);
          }}
        >
          {t("common.cancel")}
        </button>
      </form>
    );
  }

  return (
    <>
      {account.is_active ? (
        <button
          type="button"
          data-testid="user-disable"
          aria-label={t("users.disableAria", params)}
          disabled={busy}
          onClick={() => setMode("confirmDisable")}
        >
          {t("users.disable")}
        </button>
      ) : (
        <button
          type="button"
          data-testid="user-enable"
          aria-label={t("users.enableAria", params)}
          disabled={busy}
          onClick={() => changeActive(true)}
        >
          {t("users.enable")}
        </button>
      )}
      <button
        type="button"
        data-testid="user-reset"
        aria-label={t("users.resetAria", params)}
        onClick={() => setMode("reset")}
      >
        {t("users.reset")}
      </button>
    </>
  );
}
