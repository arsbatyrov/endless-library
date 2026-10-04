import { type Msg, msg, raw } from "./i18n";
import type { Book, BookInput, Loan, LoanReturn, PopularBook, Reader, ReaderInput } from "./types";

/**
 * Ошибка ответа API: хранит HTTP-код и (для ответа 422) ошибки по полям формы.
 * display это то, что показываем пользователю: либо текст сервера как есть (404, 409: поле detail, не переводится),
 * либо наше сообщение, которое переводится на язык интерфейса.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly display: Msg;
  /** Ключ: имя поля из запроса (например, "title"), значение: сообщение сервера. */
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, display: Msg, fieldErrors: Record<string, string> = {}) {
    super("text" in display ? display.text : display.key);
    this.status = status;
    this.display = display;
    this.fieldErrors = fieldErrors;
  }
}

/** Что показать, если не удалось ЗАГРУЗИТЬ данные: сообщение API или текст сетевой ошибки браузера. */
export function loadErrorMsg(error: unknown): Msg {
  if (error instanceof ApiError) {
    return error.display;
  }
  return error instanceof Error ? raw(error.message) : msg("common.unknownError");
}

/** Что показать, если не удалось ВЫПОЛНИТЬ действие (создать, удалить, выдать): сообщение API или «нет связи». */
export function actionErrorMsg(error: unknown): Msg {
  return error instanceof ApiError ? error.display : msg("common.networkError");
}

async function toApiError(response: Response): Promise<ApiError> {
  let display: Msg = msg("api.requestFailed", { status: response.status });
  const fieldErrors: Record<string, string> = {};

  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      // 404, 409: одна причина строкой (текст сервера, показываем как есть)
      display = raw(body.detail);
    } else if (Array.isArray(body.detail)) {
      // 422: список проблем, у каждой loc = ["body", "<поле>"]
      display = msg("api.checkFields");
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

  return new ApiError(response.status, display, fieldErrors);
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

export function getPopularBooks(limit: number, signal?: AbortSignal): Promise<PopularBook[]> {
  return request<PopularBook[]>(`/api/books/popular?limit=${limit}`, { signal });
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

export function getReaders(signal?: AbortSignal): Promise<Reader[]> {
  return request<Reader[]>("/api/readers", { signal });
}

export function createReader(input: ReaderInput): Promise<Reader> {
  return request<Reader>("/api/readers", jsonInit("POST", input));
}

export function updateReader(id: number, input: ReaderInput): Promise<Reader> {
  return request<Reader>(`/api/readers/${id}`, jsonInit("PUT", input));
}

export function deleteReader(id: number): Promise<void> {
  return request<void>(`/api/readers/${id}`, { method: "DELETE" });
}

/** Книги, которые сейчас на руках у читателя (ещё не возвращены). */
export function getReaderLoans(readerId: number, signal?: AbortSignal): Promise<Loan[]> {
  return request<Loan[]>(`/api/readers/${readerId}/loans`, { signal });
}

export function issueBook(bookId: number, readerId: number): Promise<Loan> {
  return request<Loan>("/api/loans", jsonInit("POST", { book_id: bookId, reader_id: readerId }));
}

export function returnBook(loanId: number): Promise<LoanReturn> {
  return request<LoanReturn>(`/api/loans/${loanId}/return`, { method: "POST" });
}
