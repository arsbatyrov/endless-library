import { useEffect, useState } from "react";

import { getUsers, loadErrorMsg } from "./api";
import { formatDate } from "./format";
import { type Key, type Msg, useI18n } from "./i18n";
import type { Account } from "./types";

type State =
  | { status: "loading" }
  | { status: "error"; message: Msg }
  | { status: "ready"; users: Account[] };

const ROLE_LABEL: Record<Account["role"], Key> = {
  reader: "users.role.reader",
  librarian: "users.role.librarian",
  admin: "users.role.admin",
};

/** Список учётных записей (раздел только для админа). Действия над ними появятся в AUTH-015. */
export function UsersPage() {
  const { t, show, locale } = useI18n();
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => (previous.status === "ready" ? previous : { status: "loading" }));
    getUsers(controller.signal)
      .then((users) => setState({ status: "ready", users }))
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
          <button type="button" data-testid="users-retry" onClick={() => setAttempt((n) => n + 1)}>
            {t("common.retry")}
          </button>
        </div>
      );
    }
    return (
      <table data-testid="users-table">
        <thead>
          <tr>
            <th>{t("users.col.login")}</th>
            <th>{t("users.col.role")}</th>
            <th>{t("users.col.status")}</th>
            <th>{t("users.col.lastLogin")}</th>
          </tr>
        </thead>
        <tbody>
          {state.users.map((user) => (
            <tr key={user.id} data-testid="user-row">
              <td data-testid="user-login">{user.username}</td>
              <td data-testid="user-role">{t(ROLE_LABEL[user.role])}</td>
              <td data-testid="user-status">{user.is_active ? t("users.active") : t("users.disabled")}</td>
              <td data-testid="user-last-login">
                {user.last_login_at ? formatDate(user.last_login_at, locale) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <section>
      <h2>{t("users.heading")}</h2>
      {renderBody()}
    </section>
  );
}
