from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Reader
from app.schemas import LoanRead, ReaderCreate, ReaderRead
from app.services.loans import ensure_reader_has_no_loans, get_active_loans

router = APIRouter(prefix="/readers", tags=["readers"])


def get_reader_or_404(reader_id: int, db: Session) -> Reader:
    reader = db.get(Reader, reader_id)
    if reader is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reader not found")
    return reader


def commit_or_409(db: Session) -> None:
    """Сохраняет изменения; если email уже занят, откатывает и возвращает 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # from exc: исходная ошибка базы сохраняется в логах как причина.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reader with this email already exists",
        ) from exc


@router.post("", response_model=ReaderRead, status_code=status.HTTP_201_CREATED)
def create_reader(data: ReaderCreate, db: Session = Depends(get_db)):
    reader = Reader(**data.model_dump())
    db.add(reader)
    commit_or_409(db)
    db.refresh(reader)
    return reader


@router.get("", response_model=list[ReaderRead])
def list_readers(db: Session = Depends(get_db)):
    return db.scalars(select(Reader).order_by(Reader.id)).all()


@router.get("/{reader_id}", response_model=ReaderRead)
def get_reader(reader_id: int, db: Session = Depends(get_db)):
    return get_reader_or_404(reader_id, db)


@router.get("/{reader_id}/loans", response_model=list[LoanRead])
def list_reader_active_loans(reader_id: int, db: Session = Depends(get_db)):
    """Книги, которые сейчас на руках у читателя (ещё не возвращены)."""
    get_reader_or_404(reader_id, db)
    return get_active_loans(db, reader_id)


@router.put("/{reader_id}", response_model=ReaderRead)
def update_reader(reader_id: int, data: ReaderCreate, db: Session = Depends(get_db)):
    reader = get_reader_or_404(reader_id, db)
    for field, value in data.model_dump().items():
        setattr(reader, field, value)
    commit_or_409(db)
    db.refresh(reader)
    return reader


@router.delete("/{reader_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reader(reader_id: int, db: Session = Depends(get_db)):
    reader = get_reader_or_404(reader_id, db)
    ensure_reader_has_no_loans(db, reader_id)
    db.delete(reader)
    db.commit()
