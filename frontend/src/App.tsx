import { type ComponentType, useState } from "react";

import { BooksPage } from "./BooksPage";
import { LoansPage } from "./LoansPage";
import { ReadersPage } from "./ReadersPage";

type Tab = "books" | "readers" | "loans";

const TABS: { id: Tab; label: string }[] = [
  { id: "books", label: "Книги" },
  { id: "readers", label: "Читатели" },
  { id: "loans", label: "Выдачи" },
];

const PAGES: Record<Tab, ComponentType> = {
  books: BooksPage,
  readers: ReadersPage,
  loans: LoansPage,
};

export function App() {
  const [tab, setTab] = useState<Tab>("books");
  const Page = PAGES[tab];

  return (
    <main>
      <h1>Библиотека</h1>

      {/* Вкладки по правилам доступности: tablist / tab / tabpanel, выбранная вкладка помечена aria-selected. */}
      <div role="tablist" aria-label="Разделы" className="tabs">
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
            {item.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        <Page />
      </div>
    </main>
  );
}
