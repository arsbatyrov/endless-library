from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import LoanCreate, LoanRead, LoanReturnRead
from app.services import loans as loan_service

router = APIRouter(prefix="/loans", tags=["loans"])


@router.post("", response_model=LoanRead, status_code=status.HTTP_201_CREATED)
def issue_book(data: LoanCreate, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    return loan_service.issue_book(db, data.book_id, data.reader_id, now)


@router.post("/{loan_id}/return", response_model=LoanReturnRead)
def return_book(loan_id: int, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    loan, fine = loan_service.return_book(db, loan_id, now)
    return LoanReturnRead(**LoanRead.model_validate(loan).model_dump(), fine=fine)
