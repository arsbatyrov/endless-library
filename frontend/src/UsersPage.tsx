import { useEffect, useState } from "react";

import { AccountActions } from "./AccountActions";
import { AccountForm } from "./AccountForm";
import { getReaders, getUsers, loadErrorMsg } from "./api";
import { formatDate } from "./format";
import { type Msg, msg, useI18n } from "./i18n";
import { ROLE_LABEL } from "./roles";
import type { Account, Reader } from "./types";

type State =
  | { status: "loading" }
  | { status: "error"; message: Msg }
  | { status: "ready"; users: Account[]; readers: Reader[] };

/** Раздел «Пользователи» (только админ): все учётные записи, создание, отключение и включение, сброс пароля. */
export function UsersPage() {
  const { t, show, locale } = useI18n();
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<Msg | null>(null);
  const [actionError, setActionError] = useState<Msg | null>(null);

  const reload = () => setAttempt((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => (previous.status === "ready" ? previous : { status: "loading" }));
    Promise.all([getUsers(controller.signal), getReaders(controller.signal)])
      .then(([users, readers]) => setState({ status: "ready", users, readers }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({ status: "error", message: loadErrorMsg(error) });
      });
    return () => controller.abort();
  }, [attempt]);

  function renderBody() {
    if (state.status === "loading") {
      return <p data-testid="users-loading">{t("common.loading")}</p>;
    }
    if (state.status === "error") {
      return (
        <div role="alert" data-testid="users-error">
          <p>{t("users.loadError", { message: show(state.message) })}</p>
          <button type="button" data-testid="users-retry" onClick={reload}>
            {t("common.retry")}
          </button>
        </div>
      );
    }
    const cardName = (id: number | null) =>
      id === null ? "—" : (state.readers.find((reader) => reader.id === id)?.name ?? `#${id}`);
    return (
      <table data-testid="users-table">
        <thead>
          <tr>
            <th>{t("users.col.login")}</th>
            <th>{t("users.col.role")}</th>
            <th>{t("users.col.card")}</th>
            <th>{t("users.col.status")}</th>
            <th>{t("users.col.lastLogin")}</th>
            <th>{t("common.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {state.users.map((user) => (
            <tr key={user.id} data-testid="user-row">
              <td data-testid="user-login">{user.username}</td>
              <td data-testid="user-role">{t(ROLE_LABEL[user.role])}</td>
              <td data-testid="user-card">{cardName(user.reader_id)}</td>
              <td data-testid="user-status">{user.is_active ? t("users.active") : t("users.disabled")}</td>
              <td data-testid="user-last-login">
                {user.last_login_at ? formatDate(user.last_login_at, locale) : "—"}
              </td>
              <td className="row-actions">
                <AccountActions
                  account={user}
                  onDone={(message) => {
                    setNotice(message);
                    setActionError(null);
                    reload();
                  }}
                  onFailed={(message) => {
                    setNotice(null);
                    setActionError(message);
                    reload();
                  }}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  const freeCards =
    state.status === "ready"
      ? state.readers.filter((reader) => !state.users.some((user) => user.reader_id === reader.id))
      : [];

  return (
    <section>
      <h2>{t("users.heading")}</h2>

      <div className="toolbar">
        <button
          type="button"
          data-testid="users-add"
          disabled={creating || state.status !== "ready"}
          onClick={() => {
            setNotice(null);
            setActionError(null);
            setCreating(true);
          }}
        >
          {t("users.add")}
        </button>
      </div>

      {notice && (
        <p role="status" className="notice" data-testid="users-notice">
          {show(notice)}
        </p>
      )}
      {actionError && (
        <p role="alert" className="form-error" data-testid="users-action-error">
          {show(actionError)}
        </p>
      )}

      {creating && (
        <AccountForm
          roles={["librarian", "admin", "reader"]}
          freeCards={freeCards}
          onCreated={(account) => {
            setNotice(msg("users.created", { username: account.username }));
            setCreating(false);
            reload();
          }}
          onCancel={() => setCreating(false)}
        />
      )}

      {renderBody()}
    </section>
  );
}
