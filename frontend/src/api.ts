import type { Book } from "./types";

/** Ошибка ответа API: хранит HTTP-код, чтобы интерфейс мог показать понятное сообщение. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);

  if (!response.ok) {
    // FastAPI кладёт причину в поле detail: строка (404, 409) или список (422).
    let message = `Ошибка запроса (код ${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      }
    } catch {
      // тело ответа не JSON: оставляем сообщение по умолчанию
    }
    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
}

export function getBooks(signal?: AbortSignal): Promise<Book[]> {
  return request<Book[]>("/api/books", { signal });
}
