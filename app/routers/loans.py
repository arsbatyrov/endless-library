from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.openapi_responses import BAD_REQUEST, CONFLICT, NOT_FOUND
from app.schemas import LoanCreate, LoanRead, LoanReturnRead, PathId
from app.services import loans as loan_service

router = APIRouter(prefix="/loans", tags=["loans"])


@router.post(
    "",
    response_model=LoanRead,
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST, **NOT_FOUND, **CONFLICT},
)
def issue_book(data: LoanCreate, db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    return loan_service.issue_book(db, data.book_id, data.reader_id, now)


@router.post(
    "/{loan_id}/return", response_model=LoanReturnRead, responses={**NOT_FOUND, **CONFLICT}
)
def return_book(loan_id: PathId, db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    loan, fine = loan_service.return_book(db, loan_id, now)
    return LoanReturnRead(**LoanRead.model_validate(loan).model_dump(), fine=fine)
