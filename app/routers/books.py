from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import BOOKS_LIST_KEY, book_key, cache
from app.database import get_db
from app.models import Book
from app.openapi_responses import BAD_REQUEST, CONFLICT, NOT_FOUND
from app.schemas import BookCreate, BookRead, PathId, PopularBook
from app.services.loans import count_loans_per_book, ensure_book_has_no_loans

router = APIRouter(prefix="/books", tags=["books"])


def get_book_or_404(book_id: int, db: Session) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book


@router.post(
    "", response_model=BookRead, status_code=status.HTTP_201_CREATED, responses={**BAD_REQUEST}
)
def create_book(data: BookCreate, db: Session = Depends(get_db)):
    book = Book(**data.model_dump())
    db.add(book)
    db.commit()
    db.refresh(book)
    cache.invalidate_books_list()
    return book


def _to_json(book: Book) -> dict:
    return BookRead.model_validate(book).model_dump(mode="json")


# Заголовок X-Cache (HIT или MISS) показывает, откуда взят ответ: из кэша или из базы. Удобно для отладки и тестов.
@router.get("", response_model=list[BookRead])
def list_books(response: Response, db: Session = Depends(get_db)):
    cached = cache.get_json(BOOKS_LIST_KEY)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached
    data = [_to_json(book) for book in db.scalars(select(Book).order_by(Book.id))]
    cache.set_json(BOOKS_LIST_KEY, data)
    response.headers["X-Cache"] = "MISS"
    return data


# Важно: /popular объявлен ДО /{book_id}, иначе слово "popular" FastAPI попытается прочитать как число id.
@router.get("/popular", response_model=list[PopularBook])
def popular_books(limit: int = Query(default=5, ge=1, le=20), db: Session = Depends(get_db)):
    """Самые выдаваемые книги. Счётчики берутся из Redis, а если их там нет, пересчитываются из базы."""
    counts = cache.popular_counts()
    if counts is None:
        counts = count_loans_per_book(db)
        cache.store_popular(counts)
    # Одинаковое число выдач: сначала книга с меньшим id (порядок должен быть предсказуемым).
    top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    books = {b.id: b for b in db.scalars(select(Book).where(Book.id.in_([i for i, _ in top])))}
    # Сами книги всегда из базы: в Redis только счётчики, поэтому название и остаток не устаревают.
    return [{"book": _to_json(books[book_id]), "loans": count} for book_id, count in top]


# PUT и DELETE на /books/popular иначе попали бы в маршруты /{book_id} и получили бы 422 («popular не число»).
# Адрес поддерживает только GET, поэтому честный ответ: 405 с перечнем разрешённых методов.
@router.api_route("/popular", methods=["PUT", "DELETE"], include_in_schema=False)
def popular_method_not_allowed():
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "GET"})


@router.get("/{book_id}", response_model=BookRead, responses={**NOT_FOUND})
def get_book(book_id: PathId, response: Response, db: Session = Depends(get_db)):
    key = book_key(book_id)
    cached = cache.get_json(key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached
    data = _to_json(get_book_or_404(book_id, db))
    cache.set_json(key, data)
    response.headers["X-Cache"] = "MISS"
    return data


@router.put("/{book_id}", response_model=BookRead, responses={**BAD_REQUEST, **NOT_FOUND})
def update_book(book_id: PathId, data: BookCreate, db: Session = Depends(get_db)):
    book = get_book_or_404(book_id, db)
    for field, value in data.model_dump().items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    cache.invalidate_book(book_id)
    return book


@router.delete(
    "/{book_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**NOT_FOUND, **CONFLICT}
)
def delete_book(book_id: PathId, db: Session = Depends(get_db)):
    book = get_book_or_404(book_id, db)
    ensure_book_has_no_loans(db, book_id)
    db.delete(book)
    db.commit()
    cache.invalidate_book(book_id)
