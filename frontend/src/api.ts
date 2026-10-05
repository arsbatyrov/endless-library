import { toApiError } from "./apiError";
import { getAccessToken, refreshAccessToken, refreshProfile, sessionExpired } from "./auth";
import type { Account, Book, BookInput, Loan, LoanReturn, PopularBook, Reader, ReaderInput } from "./types";

export { ApiError, actionErrorMsg, loadErrorMsg } from "./apiError";

/** Запрос с токеном доступа. Если сервер ответил 401 (токен истёк), токен обновляется один раз и запрос повторяется. */
async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const token = getAccessToken();
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(path, { ...init, headers });

  if (response.status === 401 && token) {
    if (!retried && (await refreshAccessToken())) {
      return request<T>(path, init, true);
    }
    // Обновить нельзя (или новый токен тоже отвергнут): сеанс закончился, показываем страницу входа.
    sessionExpired();
  }
  if (response.status === 403) {
    // Сервер отказал по роли: возможно, права изменили после входа. Перечитываем профиль, чтобы интерфейс
    // подстроился (лишние разделы и кнопки исчезнут), и показываем сообщение сервера как есть.
    await refreshProfile();
  }
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

/** Учётные записи (для админа: все; библиотекарю сервер отдаёт только читателей). */
export function getUsers(signal?: AbortSignal): Promise<Account[]> {
  return request<Account[]>("/api/users", { signal });
}
