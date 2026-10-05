import { type FormEvent, useId, useState } from "react";

import { actionErrorMsg, ApiError, changeAccountRole, resetAccountPassword, setAccountActive } from "./api";
import { refreshProfile, useSession } from "./auth";
import { type Key, type Msg, msg, useI18n } from "./i18n";
import { ROLE_LABEL, type Role } from "./roles";
import type { Account, Reader } from "./types";

interface Props {
  account: Account;
  /** Действие выполнено: сообщение для показа над таблицей (страница потом перечитывает список). */
  onDone: (message: Msg) => void;
  /** Сервер отказал (например, это последний активный админ): сообщение сервера как есть. */
  onFailed: (message: Msg) => void;
  /** Админ может сменить роль на любую. У библиотекаря этого действия нет (сервер ответил бы 403). */
  canChangeRole?: boolean;
  /** Карточки читателей без аккаунта: для перехода в роль «читатель». */
  freeCards?: Reader[];
}

type Mode = "idle" | "confirmDisable" | "reset" | "role";

const ROLES: readonly Role[] = ["reader", "librarian", "admin"];

/** Кнопки над учётной записью: отключить (с подтверждением), включить, сбросить пароль. */
export function AccountActions({ account, onDone, onFailed, canChangeRole = false, freeCards = [] }: Props) {
  const { t } = useI18n();
  const session = useSession();
  const [mode, setMode] = useState<Mode>("idle");
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [roleValue, setRoleValue] = useState<Role>(account.role);
  const [cardId, setCardId] = useState("");
  const [roleErrors, setRoleErrors] = useState<Record<string, string>>({});
  const passwordId = useId();
  const roleId = useId();
  const cardSelectId = useId();
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

  async function handleRoleChange(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setRoleErrors({});
    // Карточку шлём только при переходе В роль «читатель»: у читателя она уже есть, у остальных её нет.
    const sendCard = roleValue === "reader" && account.role !== "reader" && cardId !== "";
    try {
      await changeAccountRole(account.id, roleValue, sendCard ? Number(cardId) : undefined);
      setMode("idle");
      // Если админ сменил роль самому себе, экран подстраивается сразу, а не после первого отказа сервера.
      if (session.status === "authenticated" && session.user.id === account.id) {
        await refreshProfile();
      }
      onDone(msg(`users.roleChanged.${roleValue}` as Key, params));
    } catch (error) {
      if (error instanceof ApiError && (error.fieldErrors.reader_id || error.fieldErrors.role)) {
        setRoleErrors(error.fieldErrors);
      } else {
        setMode("idle");
        onFailed(actionErrorMsg(error));
      }
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

  if (mode === "role") {
    const becomingReader = roleValue === "reader" && account.role !== "reader";
    const leavingReader = account.role === "reader" && roleValue !== "reader";
    return (
      <form noValidate data-testid="role-form" onSubmit={handleRoleChange} aria-label={t("users.changeRoleAria", params)}>
        <div className="field">
          <label htmlFor={roleId}>{t("roleForm.role")}</label>
          <select
            id={roleId}
            data-testid="role-form-role"
            value={roleValue}
            onChange={(event) => {
              setRoleValue(event.target.value as Role);
              setRoleErrors({});
            }}
          >
            {ROLES.map((value) => (
              <option key={value} value={value}>
                {t(ROLE_LABEL[value])}
              </option>
            ))}
          </select>
        </div>
        {becomingReader && (
          <div className="field">
            <label htmlFor={cardSelectId}>{t("roleForm.reader")}</label>
            <select
              id={cardSelectId}
              data-testid="role-form-reader"
              value={cardId}
              aria-invalid={roleErrors.reader_id ? true : undefined}
              onChange={(event) => setCardId(event.target.value)}
            >
              <option value="">{t("roleForm.chooseReader")}</option>
              {freeCards.map((reader) => (
                <option key={reader.id} value={reader.id}>
                  {reader.name} ({reader.email})
                </option>
              ))}
            </select>
            {roleErrors.reader_id && (
              <p className="field-error" data-testid="role-form-error-reader_id">
                {roleErrors.reader_id}
              </p>
            )}
          </div>
        )}
        {roleErrors.role && (
          <p className="field-error" data-testid="role-form-error-role">
            {roleErrors.role}
          </p>
        )}
        {leavingReader && (
          <p className="notice" data-testid="role-form-warning">
            {t("roleForm.warning")}
          </p>
        )}
        <button type="submit" disabled={busy || roleValue === account.role} data-testid="role-form-submit">
          {t("roleForm.submit")}
        </button>
        <button
          type="button"
          data-testid="role-form-cancel"
          onClick={() => {
            setMode("idle");
            setRoleValue(account.role);
            setCardId("");
            setRoleErrors({});
          }}
        >
          {t("common.cancel")}
        </button>
      </form>
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
      {canChangeRole && (
        <button
          type="button"
          data-testid="user-role-change"
          aria-label={t("users.changeRoleAria", params)}
          onClick={() => {
            setRoleValue(account.role);
            setMode("role");
          }}
        >
          {t("users.changeRole")}
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
