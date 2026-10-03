// Форма данных, которые отдаёт API (см. BookRead в app/schemas.py).
export interface Book {
  id: number;
  title: string;
  author: string;
  year: number | null;
  copies_available: number;
}
