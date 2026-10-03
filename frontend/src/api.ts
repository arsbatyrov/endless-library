import type { Book, BookInput } from "./types";

/** Ошибка ответа API: хранит HTTP-код и (для ответа 422) ошибки по полям формы. */
export class ApiError extends Error {
  readonly status: number;
  /** Ключ: имя поля из запроса (например, "title"), значение: сообщение сервера. */
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let message = `Ошибка запроса (код ${response.status})`;
  const fieldErrors: Record<string, string> = {};

  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      // 404, 409: одна причина строкой
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      // 422: список проблем, у каждой loc = ["body", "<поле>"]
      message = "Проверьте значения полей";
      for (const item of body.detail) {
        const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : undefined;
        if (typeof field === "string" && typeof item.msg === "string" && !(field in fieldErrors)) {
          fieldErrors[field] = item.msg;
        }
      }
    }
  } catch {
    // тело ответа не JSON: оставляем сообщение по умолчанию
  }

  return new ApiError(response.status, message, fieldErrors);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);

  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    // «нет содержимого» (удаление): разбирать нечего
    return undefined as T;
  }
  return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function getBooks(signal?: AbortSignal): Promise<Book[]> {
  return request<Book[]>("/api/books", { signal });
}

export function createBook(input: BookInput): Promise<Book> {
  return request<Book>("/api/books", jsonInit("POST", input));
}

export function updateBook(id: number, input: BookInput): Promise<Book> {
  return request<Book>(`/api/books/${id}`, jsonInit("PUT", input));
}

export function deleteBook(id: number): Promise<void> {
  return request<void>(`/api/books/${id}`, { method: "DELETE" });
}
