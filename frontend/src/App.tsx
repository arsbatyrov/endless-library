import { type ComponentType, useState } from "react";

import { BooksPage } from "./BooksPage";
import { type Key, LOCALES, setLocale, useI18n } from "./i18n";
import { LoansPage } from "./LoansPage";
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
  const [tab, setTab] = useState<Tab>("books");
  const Page = PAGES[tab];

  return (
    <main>
      <header className="app-header">
        <h1>{t("app.title")}</h1>

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
      </header>

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
    </main>
  );
}
