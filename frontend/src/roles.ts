// Что видит и может каждая роль. Это только удобство интерфейса (не показывать недоступное): настоящую проверку
// всегда делает сервер, и на запрещённое действие он ответит 403.
import type { CurrentUser } from "./types";

export type Role = CurrentUser["role"];
export type Section = "books" | "readers" | "loans" | "users";

const SECTIONS: Record<Role, readonly Section[]> = {
  // Читатель: каталог с рейтингом (только чтение) и свои выдачи.
  reader: ["books", "loans"],
  // Библиотекарь: каталог, читатели и выдачи.
  librarian: ["books", "readers", "loans"],
  // Админ: всё, включая пользователей.
  admin: ["books", "readers", "loans", "users"],
};

export function sectionsFor(role: Role): readonly Section[] {
  return SECTIONS[role];
}

/** Добавлять, изменять и удалять книги могут библиотекарь и админ; читатель только читает каталог. */
export function canChangeCatalog(role: Role): boolean {
  return role !== "reader";
}
