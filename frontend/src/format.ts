import type { Locale } from "./i18n";

// Формат даты зависит от языка: по-русски 04.10.2026, по-английски 04/10/2026.
const INTL_LOCALE: Record<Locale, string> = { ru: "ru-RU", en: "en-GB" };

/** Даты приходят в UTC; показываем дату тоже в UTC, чтобы она не «плавала» от часового пояса компьютера. */
export function formatDate(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], { dateStyle: "short", timeZone: "UTC" }).format(new Date(iso));
}

/** Срок возврата прошёл? «Сейчас» считается по часам браузера (в тестах их можно подменить). */
export function isOverdue(dueIso: string, now: Date = new Date()): boolean {
  return new Date(dueIso).getTime() < now.getTime();
}
