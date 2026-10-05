// Раздел сайта хранится в адресе: /#books, /#readers, /#loans, /#users. Так раздел можно открыть по ссылке, он
// переживает перезагрузку, а кнопка «Назад» возвращает к предыдущему разделу.
//
// Запрошенный раздел может оказаться недоступным роли (читатель открыл /#readers): App показывает тогда разрешённый
// раздел и подменяет адрес. Страница запрещённого раздела при этом даже не создаётся, поэтому запросов к API нет.
import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("hashchange", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("hashchange", listener);
  };
}

function requested(): string {
  return window.location.hash.replace(/^#/, "");
}

/** Раздел, запрошенный в адресе (пустая строка, если адрес без раздела). Может быть и неизвестным, и запрещённым. */
export function useRequestedSection(): string {
  return useSyncExternalStore(subscribe, requested);
}

/** Перейти в раздел: новая запись в истории браузера. */
export function goToSection(id: string): void {
  if (requested() !== id) {
    window.location.hash = id;
  }
}

/** Подменить раздел в адресе без новой записи в истории (редирект, выход из системы). */
export function replaceSection(id: string): void {
  window.history.replaceState(null, "", `#${id}`);
  listeners.forEach((listener) => listener());
}
