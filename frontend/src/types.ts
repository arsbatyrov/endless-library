// Форма данных, которые отдаёт API (см. BookRead в app/schemas.py).
export interface Book {
  id: number;
  title: string;
  author: string;
  year: number | null;
  copies_available: number;
}

// Данные, которые форма отправляет при создании и изменении книги (см. BookCreate).
// Пустые числовые поля превращаются в null: проверку и сообщение об ошибке даёт сервер.
export interface BookInput {
  title: string;
  author: string;
  year: number | null;
  copies_available: number | null;
}
