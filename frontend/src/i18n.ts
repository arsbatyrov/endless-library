// Локализация интерфейса: русский и английский.
//
// Как это устроено:
// - Все тексты лежат в словаре `ru` (ключ -> строка). Словарь `en` обязан содержать ТЕ ЖЕ ключи: тип
//   Record<Key, string> не даёт собрать проект, если перевод какого-то ключа забыт.
// - В строках можно использовать подстановки {имя}: t("books.added", { title: "Дюна" }).
// - Выбранный язык хранится в localStorage; если выбора ещё не было, берётся язык браузера (ru или en).
// - Тексты, которые приходят С СЕРВЕРА (поле detail в ответах об ошибках), не переводятся: их показывают как есть.
import { useSyncExternalStore } from "react";

export type Locale = "ru" | "en";
export const LOCALES: readonly Locale[] = ["ru", "en"];

const ru = {
  "app.title": "Библиотека",
  "app.sections": "Разделы",
  "locale.label": "Язык",
  "locale.ru": "Русский",
  "locale.en": "English",

  "tab.books": "Книги",
  "tab.readers": "Читатели",
  "tab.loans": "Выдачи",

  "common.loading": "Загрузка…",
  "common.retry": "Повторить",
  "common.save": "Сохранить",
  "common.cancel": "Отмена",
  "common.edit": "Изменить",
  "common.delete": "Удалить",
  "common.confirmDelete": "Да, удалить",
  "common.actions": "Действия",
  "common.unknownError": "Неизвестная ошибка",
  "common.networkError": "Не удалось связаться с сервером",

  "api.requestFailed": "Ошибка запроса (код {status})",
  "api.checkFields": "Проверьте значения полей",

  "books.heading": "Книги",
  "books.add": "Добавить книгу",
  "books.loadError": "Не удалось загрузить книги: {message}",
  "books.empty": "Пока нет ни одной книги",
  "books.col.title": "Название",
  "books.col.author": "Автор",
  "books.col.year": "Год",
  "books.col.inStock": "В наличии",
  "books.editAria": "Изменить «{title}»",
  "books.deleteAria": "Удалить «{title}»",
  "books.deleteQuestion": "Удалить «{title}»?",
  "books.added": "Книга «{title}» добавлена",
  "books.saved": "Изменения книги «{title}» сохранены",
  "books.deleted": "Книга «{title}» удалена",

  "bookForm.new": "Новая книга",
  "bookForm.edit": "Изменить книгу",
  "bookForm.editAria": "Изменение книги",
  "bookForm.title": "Название",
  "bookForm.author": "Автор",
  "bookForm.year": "Год издания",
  "bookForm.copies": "Количество экземпляров",

  "readers.heading": "Читатели",
  "readers.add": "Добавить читателя",
  "readers.loadError": "Не удалось загрузить читателей: {message}",
  "readers.empty": "Пока нет ни одного читателя",
  "readers.col.name": "Имя",
  "readers.col.email": "Email",
  "readers.editAria": "Изменить «{name}»",
  "readers.deleteAria": "Удалить «{name}»",
  "readers.deleteQuestion": "Удалить «{name}»?",
  "readers.added": "Читатель «{name}» добавлен",
  "readers.saved": "Изменения читателя «{name}» сохранены",
  "readers.deleted": "Читатель «{name}» удалён",

  "readerForm.new": "Новый читатель",
  "readerForm.edit": "Изменить читателя",
  "readerForm.editAria": "Изменение читателя",
  "readerForm.name": "Имя",
  "readerForm.email": "Email",

  "loans.heading": "Выдачи",
  "loans.loadError": "Не удалось загрузить данные: {message}",
  "loans.listError": "Не удалось загрузить выдачи: {message}",
  "loans.pickReader": "Выберите читателя, чтобы увидеть его книги и выдать новую",
  "loans.empty": "У читателя нет книг на руках",
  "loans.col.book": "Книга",
  "loans.col.issued": "Выдана",
  "loans.col.due": "Вернуть до",
  "loans.overdue": "просрочено",
  "loans.returnAria": "Вернуть «{title}»",
  "loans.return": "Вернуть",
  "loans.readerLabel": "Читатель",
  "loans.chooseReader": "— выберите читателя —",
  "loans.issueHeading": "Выдать книгу",
  "loans.bookLabel": "Книга",
  "loans.chooseBook": "— выберите книгу —",
  "loans.bookOption": "{title} — {author} (в наличии: {copies})",
  "loans.issue": "Выдать",
  "loans.issued": "Книга «{title}» выдана, вернуть до {date}",
  "loans.returned": "Книга «{title}» возвращена. Штраф: {fine}",
  "loans.unknownBook": "книга №{id}",

  "popular.heading": "Популярные книги",
  "popular.error": "Рейтинг временно недоступен",
  "popular.empty": "Книги пока не выдавали",
  "popular.loans": "выдач",
} as const;

export type Key = keyof typeof ru;

const en: Record<Key, string> = {
  "app.title": "Library",
  "app.sections": "Sections",
  "locale.label": "Language",
  "locale.ru": "Русский",
  "locale.en": "English",

  "tab.books": "Books",
  "tab.readers": "Readers",
  "tab.loans": "Loans",

  "common.loading": "Loading…",
  "common.retry": "Retry",
  "common.save": "Save",
  "common.cancel": "Cancel",
  "common.edit": "Edit",
  "common.delete": "Delete",
  "common.confirmDelete": "Yes, delete",
  "common.actions": "Actions",
  "common.unknownError": "Unknown error",
  "common.networkError": "Could not reach the server",

  "api.requestFailed": "Request failed (code {status})",
  "api.checkFields": "Please check the field values",

  "books.heading": "Books",
  "books.add": "Add book",
  "books.loadError": "Could not load books: {message}",
  "books.empty": "There are no books yet",
  "books.col.title": "Title",
  "books.col.author": "Author",
  "books.col.year": "Year",
  "books.col.inStock": "In stock",
  "books.editAria": "Edit “{title}”",
  "books.deleteAria": "Delete “{title}”",
  "books.deleteQuestion": "Delete “{title}”?",
  "books.added": "Book “{title}” added",
  "books.saved": "Changes to book “{title}” saved",
  "books.deleted": "Book “{title}” deleted",

  "bookForm.new": "New book",
  "bookForm.edit": "Edit book",
  "bookForm.editAria": "Editing a book",
  "bookForm.title": "Title",
  "bookForm.author": "Author",
  "bookForm.year": "Year of publication",
  "bookForm.copies": "Number of copies",

  "readers.heading": "Readers",
  "readers.add": "Add reader",
  "readers.loadError": "Could not load readers: {message}",
  "readers.empty": "There are no readers yet",
  "readers.col.name": "Name",
  "readers.col.email": "Email",
  "readers.editAria": "Edit “{name}”",
  "readers.deleteAria": "Delete “{name}”",
  "readers.deleteQuestion": "Delete “{name}”?",
  "readers.added": "Reader “{name}” added",
  "readers.saved": "Changes to reader “{name}” saved",
  "readers.deleted": "Reader “{name}” deleted",

  "readerForm.new": "New reader",
  "readerForm.edit": "Edit reader",
  "readerForm.editAria": "Editing a reader",
  "readerForm.name": "Name",
  "readerForm.email": "Email",

  "loans.heading": "Loans",
  "loans.loadError": "Could not load data: {message}",
  "loans.listError": "Could not load loans: {message}",
  "loans.pickReader": "Choose a reader to see their books and issue a new one",
  "loans.empty": "The reader has no books on loan",
  "loans.col.book": "Book",
  "loans.col.issued": "Issued",
  "loans.col.due": "Due",
  "loans.overdue": "overdue",
  "loans.returnAria": "Return “{title}”",
  "loans.return": "Return",
  "loans.readerLabel": "Reader",
  "loans.chooseReader": "— choose a reader —",
  "loans.issueHeading": "Issue a book",
  "loans.bookLabel": "Book",
  "loans.chooseBook": "— choose a book —",
  "loans.bookOption": "{title} — {author} (in stock: {copies})",
  "loans.issue": "Issue",
  "loans.issued": "Book “{title}” issued, due {date}",
  "loans.returned": "Book “{title}” returned. Fine: {fine}",
  "loans.unknownBook": "book #{id}",

  "popular.heading": "Popular books",
  "popular.error": "The ranking is temporarily unavailable",
  "popular.empty": "No books have been issued yet",
  "popular.loans": "loans",
};

const DICTIONARIES: Record<Locale, Record<Key, string>> = { ru, en };
const STORAGE_KEY = "library.locale";

export type Params = Record<string, string | number>;

/** Сообщение для показа пользователю: либо ключ перевода (переводится при каждом показе), либо готовый текст сервера. */
export type Msg = { key: Key; params?: Params } | { text: string };

export const msg = (key: Key, params?: Params): Msg => ({ key, params });
/** Текст, который приходит с сервера: показывается как есть, на язык интерфейса не переводится. */
export const raw = (text: string): Msg => ({ text });

function isLocale(value: unknown): value is Locale {
  return value === "ru" || value === "en";
}

function detectLocale(): Locale {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(saved)) {
      return saved;
    }
  } catch {
    // localStorage может быть недоступен (приватный режим): работаем без сохранения выбора
  }
  return navigator.language.toLowerCase().startsWith("ru") ? "ru" : "en";
}

let current: Locale = detectLocale();
const listeners = new Set<() => void>();

function applyToDocument() {
  document.documentElement.lang = current;
  document.title = t("app.title");
}

export function getLocale(): Locale {
  return current;
}

export function setLocale(locale: Locale): void {
  if (locale === current) {
    return;
  }
  current = locale;
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // см. выше
  }
  applyToDocument();
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Текст на текущем языке. Подстановки {имя} заменяются значениями из params. */
export function t(key: Key, params?: Params): string {
  const template = DICTIONARIES[current][key];
  return params ? template.replace(/\{(\w+)\}/g, (match, name) => String(params[name] ?? match)) : template;
}

/** Показывает сообщение: ключ переводится на текущий язык, текст сервера остаётся как есть. */
export function show(message: Msg): string {
  return "text" in message ? message.text : t(message.key, message.params);
}

/** Хук: компонент перерисовывается при смене языка. Возвращает функции t и show. */
export function useI18n() {
  const locale = useSyncExternalStore(subscribe, getLocale);
  return { locale, t, show };
}

applyToDocument();
