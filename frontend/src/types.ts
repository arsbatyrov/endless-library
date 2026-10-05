import type { Msg } from "./i18n";

// Форма данных, которые отдаёт API (см. BookRead в app/schemas.py).
export interface Book {
  id: number;
  title: string;
  author: string;
  year: number | null;
  copies_available: number;
}

// См. PopularBook в app/schemas.py: книга и число её выдач за всё время.
export interface PopularBook {
  book: Book;
  loans: number;
}

// Данные, которые форма отправляет при создании и изменении книги (см. BookCreate).
// Пустые числовые поля превращаются в null: проверку и сообщение об ошибке даёт сервер.
export interface BookInput {
  title: string;
  author: string;
  year: number | null;
  copies_available: number | null;
}

// См. ReaderRead и ReaderCreate в app/schemas.py.
export interface Reader {
  id: number;
  name: string;
  email: string;
}

export interface ReaderInput {
  name: string;
  email: string;
}

// См. LoanRead и LoanReturnRead в app/schemas.py. Даты приходят строками ISO 8601 в UTC.
export interface Loan {
  id: number;
  book_id: number;
  reader_id: number;
  issued_at: string;
  due_at: string;
  returned_at: string | null;
}

/** Ответ на возврат книги: выдача плюс размер штрафа. */
export interface LoanReturn extends Loan {
  fine: number;
}

/** Ошибка, которую форма показывает пользователю: общее сообщение и сообщения по полям. */
export interface FormError {
  display: Msg;
  fieldErrors: Record<string, string>;
}

/** Кто вошёл (ответ GET /api/auth/me). */
export interface CurrentUser {
  id: number;
  username: string;
  role: "reader" | "librarian" | "admin";
  reader_id: number | null;
}

/** Учётная запись в списке пользователей (GET /api/users, см. UserRead в app/schemas.py). Хеша пароля тут нет. */
export interface Account {
  id: number;
  username: string;
  role: CurrentUser["role"];
  reader_id: number | null;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

/** Данные новой учётной записи (см. UserCreate в app/schemas.py). */
export interface AccountInput {
  username: string;
  password: string;
  role: CurrentUser["role"];
  reader_id: number | null;
}
