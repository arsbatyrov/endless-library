import { type ComponentType, useEffect, useState } from "react";

import { logout, useSession } from "./auth";
import { BooksPage } from "./BooksPage";
import { type Key, LOCALES, setLocale, useI18n } from "./i18n";
import { LoansPage } from "./LoansPage";
import { LoginPage } from "./LoginPage";
import { ReadersPage } from "./ReadersPage";

type Tab = "books" | "readers" | "loans";

const TABS: { id: Tab; label: Key }[] = [
  { id: "books", label: "tab.books" },
  { id: "readers", label: "tab.readers" },
  { id: "loans", label: "tab.loans" },
];

const PAGES: Record<Tab, ComponentType> = {
  books: BooksPage,
  readers: ReadersPage,
  loans: LoansPage,
};

export function App() {
  const { t, locale } = useI18n();
  const session = useSession();
  const [tab, setTab] = useState<Tab>("books");
  const Page = PAGES[tab];

  // После выхода (или потери сеанса) следующий вход начинается с раздела «Книги», а не с вкладки прошлого пользователя.
  useEffect(() => {
    if (session.status !== "authenticated") {
      setTab("books");
    }
  }, [session.status]);

  return (
    <main>
      <header className="app-header">
        <h1>{t("app.title")}</h1>

        <div className="header-tools">
          {/* Выбор языка. aria-pressed сообщает программам экранного доступа, какой язык включён. */}
          <div role="group" aria-label={t("locale.label")} className="locale-switcher">
            {LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                lang={code}
                aria-pressed={locale === code}
                aria-label={t(`locale.${code}`)}
                data-testid={`locale-${code}`}
                onClick={() => setLocale(code)}
              >
                {code.toUpperCase()}
              </button>
            ))}
          </div>

          {session.status === "authenticated" && (
            <div
              role="group"
              className="user-box"
              aria-label={t("auth.signedInAs", { username: session.user.username })}
            >
              <span data-testid="current-user">{session.user.username}</span>
              <button type="button" data-testid="logout" onClick={() => void logout()}>
                {t("auth.logout")}
              </button>
            </div>
          )}
        </div>
      </header>

      {session.status === "restoring" && <p data-testid="session-restoring">{t("auth.restoring")}</p>}
      {session.status === "anonymous" && <LoginPage expired={session.expired} />}
      {session.status === "authenticated" && (
        <>
          {/* Вкладки по правилам доступности: tablist / tab / tabpanel, выбранная вкладка помечена aria-selected. */}
          <div role="tablist" aria-label={t("app.sections")} className="tabs">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                id={`tab-${item.id}`}
                aria-selected={tab === item.id}
                aria-controls={`panel-${item.id}`}
                data-testid={`tab-${item.id}`}
                onClick={() => setTab(item.id)}
              >
                {t(item.label)}
              </button>
            ))}
          </div>

          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            <Page />
          </div>
        </>
      )}
    </main>
  );
}
