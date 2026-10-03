from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Book
from app.schemas import BookCreate, BookRead

router = APIRouter(prefix="/books", tags=["books"])


def get_book_or_404(book_id: int, db: Session) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book


@router.post("", response_model=BookRead, status_code=status.HTTP_201_CREATED)
def create_book(data: BookCreate, db: Session = Depends(get_db)):
    book = Book(**data.model_dump())
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


@router.get("", response_model=list[BookRead])
def list_books(db: Session = Depends(get_db)):
    return db.scalars(select(Book).order_by(Book.id)).all()


@router.get("/{book_id}", response_model=BookRead)
def get_book(book_id: int, db: Session = Depends(get_db)):
    return get_book_or_404(book_id, db)


@router.put("/{book_id}", response_model=BookRead)
def update_book(book_id: int, data: BookCreate, db: Session = Depends(get_db)):
    book = get_book_or_404(book_id, db)
    for field, value in data.model_dump().items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return book


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = get_book_or_404(book_id, db)
    db.delete(book)
    db.commit()
