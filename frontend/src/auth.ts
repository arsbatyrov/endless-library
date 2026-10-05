// Вход в систему: токен доступа и состояние сеанса.
//
// Безопасность:
// - Токен доступа (живёт 15 минут) хранится ТОЛЬКО в памяти этой страницы (переменная ниже). Ни localStorage, ни
//   sessionStorage, ни обычные cookie: скрипт, внедрённый в страницу, не найдёт его в хранилищах.
// - Долгоживущий токен обновления лежит в httpOnly-cookie, которую JavaScript прочитать не может. После перезагрузки
//   страницы вход восстанавливается «тихо»: запросом POST /api/auth/refresh (браузер сам прикладывает cookie).
// - Пароль нигде не сохраняется: он живёт в поле формы и уходит в одном запросе.
import { useSyncExternalStore } from "react";

import { toApiError } from "./apiError";
import { replaceSection } from "./section";
import type { CurrentUser } from "./types";

export type Session =
  | { status: "restoring" }
  | { status: "anonymous"; expired: boolean }
  | { status: "authenticated"; user: CurrentUser };

let accessToken: string | null = null;
let session: Session = { status: "restoring" };
const listeners = new Set<() => void>();

function setSession(next: Session): void {
  session = next;
  listeners.forEach((listener) => listener());
}

export function getSession(): Session {
  return session;
}

export function getAccessToken(): string | null {
  return accessToken;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useSession(): Session {
  return useSyncExternalStore(subscribe, getSession);
}

interface TokenResponse {
  access_token: string;
}

async function fetchMe(token: string): Promise<CurrentUser> {
  const response = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as CurrentUser;
}

/** Вход по логину и паролю. Ошибка сервера (неверные данные, блокировка) пробрасывается как ApiError. */
export async function login(username: string, password: string): Promise<void> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  const { access_token } = (await response.json()) as TokenResponse;
  const user = await fetchMe(access_token);
  accessToken = access_token;
  setSession({ status: "authenticated", user });
}

let reloadingProfile: Promise<void> | null = null;

/**
 * Перечитывает «кто я» у сервера. Вызывается, когда сервер ответил 403: возможно, роль изменили уже после входа, и
 * интерфейс должен показывать то, что роль разрешает СЕЙЧАС (разделы, кнопки). Одновременные вызовы делят один запрос.
 */
export function refreshProfile(): Promise<void> {
  reloadingProfile ??= (async () => {
    try {
      if (session.status === "authenticated" && accessToken) {
        const user = await fetchMe(accessToken);
        const current = session.user;
        if (user.role !== current.role || user.reader_id !== current.reader_id) {
          setSession({ status: "authenticated", user });
        }
      }
    } catch {
      // нет связи или токен отвергнут: прежний профиль остаётся, а 401 обработает общий механизм
    } finally {
      reloadingProfile = null;
    }
  })();
  return reloadingProfile;
}

let refreshing: Promise<boolean> | null = null;

/**
 * Получает новый токен доступа по cookie обновления. Одновременные вызовы делят один запрос: если несколько
 * запросов страницы получили 401 разом, сервер увидит одно обновление (иначе вторая попытка с уже заменённым
 * токеном выглядела бы как кража и завершила бы сеанс).
 */
export function refreshAccessToken(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const response = await fetch("/api/auth/refresh", { method: "POST" });
      if (!response.ok) {
        return false;
      }
      accessToken = ((await response.json()) as TokenResponse).access_token;
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

/** При загрузке страницы: если cookie обновления ещё действует, молча входим; иначе показываем страницу входа. */
export async function restoreSession(): Promise<void> {
  try {
    if (await refreshAccessToken()) {
      const user = await fetchMe(accessToken as string);
      setSession({ status: "authenticated", user });
      return;
    }
  } catch {
    // нет связи или /me не ответил: остаёмся без входа
  }
  accessToken = null;
  setSession({ status: "anonymous", expired: false });
}

/** Сеанс закончился (не удалось обновить токен): забываем токен и показываем страницу входа с пояснением. */
export function sessionExpired(): void {
  if (session.status === "authenticated") {
    accessToken = null;
    setSession({ status: "anonymous", expired: true });
  }
}

/** Выход: сервер отзывает токен обновления и очищает cookie; токен доступа забываем сразу. */
export async function logout(): Promise<void> {
  accessToken = null;
  // Следующий вход начинается с раздела «Книги», а не с раздела прошлого пользователя.
  replaceSection("books");
  setSession({ status: "anonymous", expired: false });
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch {
    // нет связи: на экране уже страница входа, а токен в памяти забыт
  }
}

