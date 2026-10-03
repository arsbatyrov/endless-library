// Даты приходят в UTC; показываем дату тоже в UTC, чтобы она не «плавала» от часового пояса компьютера.
const dateFormat = new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeZone: "UTC" });

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}

/** Срок возврата прошёл? «Сейчас» считается по часам браузера (в тестах их можно подменить). */
export function isOverdue(dueIso: string, now: Date = new Date()): boolean {
  return new Date(dueIso).getTime() < now.getTime();
}
