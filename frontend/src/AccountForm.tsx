import { type FormEvent, useState } from "react";

import { ApiError, createUser } from "./api";
import { FormField } from "./FormField";
import { type Msg, msg, useI18n } from "./i18n";
import { ROLE_LABEL, type Role } from "./roles";
import type { Account, Reader } from "./types";

/** Ошибка формы: общее сообщение (его может не быть, если ответ отнесён к полю) и сообщения по полям. */
interface AccountFormError {
  display: Msg | null;
  fieldErrors: Record<string, string>;
}

interface Props {
  /** Роли, которые можно выбрать: админ видит все, у библиотекаря (и в форме из карточки читателя) только «читатель». */
  roles: readonly Role[];
  /** Если задана, аккаунт создаётся для этой карточки читателя (выбирать карточку не нужно). */
  card?: Reader;
  /** Карточки читателей, у которых ещё нет аккаунта (для выбора, когда карточка не задана). */
  freeCards?: Reader[];
  onCreated: (account: Account) => void;
  onCancel: () => void;
}

/**
 * Куда в форме отнести ответ сервера. 422 приходит уже по полям. А «логин занят» (409) и «карточка не найдена» (404)
 * сервер присылает одной строкой: по смыслу отнесём её к полю логина или карточки. Текст всегда показываем как есть.
 */
function toFormError(error: unknown): AccountFormError {
  if (!(error instanceof ApiError)) {
    return { display: msg("common.networkError"), fieldErrors: {} };
  }
  const text = "text" in error.display ? error.display.text : "";
  if (error.status === 409 || error.status === 404) {
    const field = /login/i.test(text) ? "username" : /card|reader/i.test(text) ? "reader_id" : null;
    if (field) {
      return { display: null, fieldErrors: { [field]: text } };
    }
  }
  return { display: error.display, fieldErrors: error.fieldErrors };
}

/** Форма создания учётной записи. Ошибки сервера (пароль короче 8 символов, логин занят) стоят под своим полем. */
export function AccountForm({ roles, card, freeCards = [], onCreated, onCancel }: Props) {
  const { t, show } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>(roles[0]);
  const [readerId, setReaderId] = useState(card ? String(card.id) : "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<AccountFormError | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await createUser({
        username,
        password,
        role,
        reader_id: role === "reader" && readerId !== "" ? Number(readerId) : null,
      });
      onCreated(created);
    } catch (caught) {
      setError(toFormError(caught));
    } finally {
      setSubmitting(false);
    }
  }

  const errors = error?.fieldErrors ?? {};
  const title = card ? t("accountForm.titleForCard", { name: card.name }) : t("accountForm.title");

  return (
    <form onSubmit={handleSubmit} noValidate data-testid="account-form" aria-label={title}>
      <h3>{title}</h3>

      {error?.display && (
        <p role="alert" className="form-error" data-testid="account-form-error">
          {show(error.display)}
        </p>
      )}

      <FormField
        testIdPrefix="account-form"
        name="username"
        label={t("accountForm.username")}
        value={username}
        onChange={setUsername}
        error={errors.username}
        autoComplete="off"
      />
      <FormField
        testIdPrefix="account-form"
        name="password"
        label={t("accountForm.password")}
        type="password"
        value={password}
        onChange={setPassword}
        error={errors.password}
        autoComplete="new-password"
      />

      <div className="field">
        <label htmlFor="account-form-role">{t("accountForm.role")}</label>
        <select
          id="account-form-role"
          data-testid="account-form-role"
          value={role}
          disabled={roles.length === 1}
          onChange={(event) => setRole(event.target.value as Role)}
        >
          {roles.map((value) => (
            <option key={value} value={value}>
              {t(ROLE_LABEL[value])}
            </option>
          ))}
        </select>
        {errors.role && (
          <p className="field-error" data-testid="account-form-error-role">
            {errors.role}
          </p>
        )}
      </div>

      {role === "reader" && card && <p data-testid="account-form-card">{t("accountForm.card", { name: card.name })}</p>}
      {role === "reader" && !card && (
        <div className="field">
          <label htmlFor="account-form-reader">{t("accountForm.reader")}</label>
          <select
            id="account-form-reader"
            data-testid="account-form-reader"
            value={readerId}
            aria-invalid={errors.reader_id ? true : undefined}
            onChange={(event) => setReaderId(event.target.value)}
          >
            <option value="">{t("accountForm.chooseReader")}</option>
            {freeCards.map((reader) => (
              <option key={reader.id} value={reader.id}>
                {reader.name} ({reader.email})
              </option>
            ))}
          </select>
        </div>
      )}
      {role === "reader" && errors.reader_id && (
        <p className="field-error" data-testid="account-form-error-reader_id">
          {errors.reader_id}
        </p>
      )}

      <div className="actions">
        <button type="submit" disabled={submitting} data-testid="account-form-submit">
          {t("accountForm.create")}
        </button>
        <button type="button" onClick={onCancel} data-testid="account-form-cancel">
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}
