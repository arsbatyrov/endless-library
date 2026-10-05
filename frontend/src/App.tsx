import { type ComponentType, useEffect } from "react";

import { logout, useSession } from "./auth";
import { BooksPage } from "./BooksPage";
import { type Key, LOCALES, setLocale, useI18n } from "./i18n";
import { LoansPage } from "./LoansPage";
import { LoginPage } from "./LoginPage";
import { MyLoansPage } from "./MyLoansPage";
import { ReadersPage } from "./ReadersPage";
import { type Role, type Section, sectionsFor } from "./roles";
import { goToSection, replaceSection, useRequestedSection } from "./section";
import { UsersPage } from "./UsersPage";

const LABELS: Record<Section, Key> = {
  books: "tab.books",
  readers: "tab.readers",
  loans: "tab.loans",
  users: "tab.users",
};

/** Страница раздела для роли: «Выдачи» читателя (только свои книги) и персонала (выдача и возврат) это разные страницы. */
function pageFor(section: Section, role: Role): ComponentType {
  switch (section) {
    case "books":
      return BooksPage;
    case "readers":
      return ReadersPage;
    case "loans":
      return role === "reader" ? MyLoansPage : LoansPage;
    case "users":
      return UsersPage;
  }
}

export function App() {
  const { t, locale } = useI18n();
  const session = useSession();
  const requested = useRequestedSection();

  // Раздел берётся из адреса, но только из тех, что роль разрешает. Запрошенный запрещённый (читатель открыл
  // /#readers) заменяется на первый разрешённый, и адрес подменяется. Страница запрещённого раздела даже не создаётся,
  // поэтому запросов к API за ним нет.
  const role = session.status === "authenticated" ? session.user.role : null;
  const allowed: readonly Section[] = role ? sectionsFor(role) : [];
  const tab = allowed.find((section) => section === requested) ?? allowed[0];

  useEffect(() => {
    if (tab !== undefined && requested !== "" && requested !== tab) {
      replaceSection(tab);
    }
  }, [tab, requested]);

  const Page = tab !== undefined && role !== null ? pageFor(tab, role) : null;

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
      {session.status === "authenticated" && tab !== undefined && Page !== null && (
        <>
          {/* Вкладки по правилам доступности: tablist / tab / tabpanel, выбранная вкладка помечена aria-selected. */}
          <div role="tablist" aria-label={t("app.sections")} className="tabs">
            {allowed.map((section) => (
              <button
                key={section}
                type="button"
                role="tab"
                id={`tab-${section}`}
                aria-selected={tab === section}
                aria-controls={`panel-${section}`}
                data-testid={`tab-${section}`}
                onClick={() => goToSection(section)}
              >
                {t(LABELS[section])}
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
