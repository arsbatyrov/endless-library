from datetime import datetime, timedelta, timezone

import pytest

from app.models import Loan, UTCDateTime, utcnow
from tests.factories import make_book, make_reader

PLUS_THREE = timezone(timedelta(hours=3))


def test_naive_datetime_is_rejected():
    naive = datetime(2026, 1, 1, 12, 0)

    with pytest.raises(ValueError, match="Naive datetime"):
        UTCDateTime().process_bind_param(naive, dialect=None)


def test_none_is_passed_through_on_save_and_load():
    column_type = UTCDateTime()

    assert column_type.process_bind_param(None, dialect=None) is None
    assert column_type.process_result_value(None, dialect=None) is None


def test_aware_datetime_in_other_timezone_is_stored_as_the_same_instant_in_utc(db):
    book, reader = make_book(db), make_reader(db)
    local_time = datetime(2026, 1, 1, 15, 0, tzinfo=PLUS_THREE)  # это 12:00 UTC
    loan = Loan(book_id=book.id, reader_id=reader.id, issued_at=local_time, due_at=local_time)
    db.add(loan)
    db.commit()

    db.expire_all()  # заставляем перечитать значения из базы, а не из памяти сессии
    saved = db.get(Loan, loan.id)

    assert saved.due_at == local_time                  # тот же момент времени
    assert saved.due_at.utcoffset() == timedelta(0)    # и снова с поясом UTC
    assert saved.due_at.hour == 12


def test_issued_at_defaults_to_current_utc_time(db):
    book, reader = make_book(db), make_reader(db)
    before = utcnow()
    loan = Loan(book_id=book.id, reader_id=reader.id, due_at=before)
    db.add(loan)
    db.commit()

    db.expire_all()
    saved = db.get(Loan, loan.id)

    assert before <= saved.issued_at <= utcnow()
