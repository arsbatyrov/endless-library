from datetime import UTC, datetime, timedelta

import pytest

from app.services.errors import BusinessRuleError, NotFoundError
from app.services.loans import (
    LOAN_PERIOD_DAYS,
    MAX_ACTIVE_LOANS,
    ensure_book_has_no_loans,
    ensure_reader_has_no_loans,
    get_active_loans,
    issue_book,
    return_book,
)
from tests.factories import make_book, make_reader

# «Сейчас» в тестах задаём сами: так не нужно ждать, чтобы получить просрочку.
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


# ---------- выдача ----------


def test_issue_book_creates_loan_with_due_date(db):
    book = make_book(db, copies=2)
    reader = make_reader(db)

    loan = issue_book(db, book.id, reader.id, NOW)

    assert loan.book_id == book.id
    assert loan.reader_id == reader.id
    assert loan.issued_at == NOW
    assert loan.due_at == NOW + timedelta(days=LOAN_PERIOD_DAYS)
    assert loan.returned_at is None


def test_issue_book_decreases_available_copies(db):
    book = make_book(db, copies=2)
    reader = make_reader(db)

    issue_book(db, book.id, reader.id, NOW)

    assert book.copies_available == 1


def test_issue_book_fails_when_no_copies_left(db):
    book = make_book(db, copies=0)
    reader = make_reader(db)

    with pytest.raises(BusinessRuleError, match="No copies"):
        issue_book(db, book.id, reader.id, NOW)


def test_issue_last_copy_succeeds_then_next_reader_is_refused(db):
    book = make_book(db, copies=1)
    first, second = make_reader(db), make_reader(db)

    issue_book(db, book.id, first.id, NOW)

    with pytest.raises(BusinessRuleError, match="No copies"):
        issue_book(db, book.id, second.id, NOW)


def test_issue_book_fails_for_unknown_reader(db):
    book = make_book(db)

    with pytest.raises(NotFoundError, match="Reader"):
        issue_book(db, book.id, 999, NOW)


def test_issue_book_fails_for_unknown_book(db):
    reader = make_reader(db)

    with pytest.raises(NotFoundError, match="Book"):
        issue_book(db, 999, reader.id, NOW)


@pytest.mark.parametrize("already_on_hands", range(MAX_ACTIVE_LOANS))
def test_reader_below_limit_can_take_another_book(db, already_on_hands):
    book = make_book(db, copies=10)
    reader = make_reader(db)
    for _ in range(already_on_hands):
        issue_book(db, book.id, reader.id, NOW)

    loan = issue_book(db, book.id, reader.id, NOW)

    assert loan.id is not None


def test_reader_at_limit_cannot_take_another_book(db):
    book = make_book(db, copies=10)
    reader = make_reader(db)
    for _ in range(MAX_ACTIVE_LOANS):
        issue_book(db, book.id, reader.id, NOW)

    with pytest.raises(BusinessRuleError, match="active loans"):
        issue_book(db, book.id, reader.id, NOW)


def test_returned_books_do_not_count_towards_limit(db):
    book = make_book(db, copies=10)
    reader = make_reader(db)
    loans = [issue_book(db, book.id, reader.id, NOW) for _ in range(MAX_ACTIVE_LOANS)]
    return_book(db, loans[0].id, NOW)

    new_loan = issue_book(db, book.id, reader.id, NOW)

    assert new_loan.returned_at is None


def test_limit_is_per_reader(db):
    book = make_book(db, copies=10)
    busy, free = make_reader(db), make_reader(db)
    for _ in range(MAX_ACTIVE_LOANS):
        issue_book(db, book.id, busy.id, NOW)

    loan = issue_book(db, book.id, free.id, NOW)

    assert loan.reader_id == free.id


# ---------- возврат ----------


def test_return_book_marks_loan_and_restores_copy(db):
    book = make_book(db, copies=1)
    reader = make_reader(db)
    loan = issue_book(db, book.id, reader.id, NOW)
    returned_at = NOW + timedelta(days=3)

    returned_loan, fine = return_book(db, loan.id, returned_at)

    assert returned_loan.returned_at == returned_at
    assert book.copies_available == 1
    assert fine == 0


def test_return_after_due_date_charges_fine(db):
    book = make_book(db)
    reader = make_reader(db)
    loan = issue_book(db, book.id, reader.id, NOW)
    three_days_late = NOW + timedelta(days=LOAN_PERIOD_DAYS + 3)

    _, fine = return_book(db, loan.id, three_days_late)

    assert fine == 30


def test_return_book_twice_is_refused(db):
    book = make_book(db)
    reader = make_reader(db)
    loan = issue_book(db, book.id, reader.id, NOW)
    return_book(db, loan.id, NOW)

    with pytest.raises(BusinessRuleError, match="already returned"):
        return_book(db, loan.id, NOW)


def test_second_return_does_not_add_extra_copy(db):
    book = make_book(db, copies=1)
    reader = make_reader(db)
    loan = issue_book(db, book.id, reader.id, NOW)
    return_book(db, loan.id, NOW)

    with pytest.raises(BusinessRuleError):
        return_book(db, loan.id, NOW)

    assert book.copies_available == 1


def test_return_unknown_loan_fails(db):
    with pytest.raises(NotFoundError, match="Loan"):
        return_book(db, 999, NOW)


# ---------- списки и защита от удаления ----------


def test_active_loans_exclude_returned_ones(db):
    book = make_book(db, copies=5)
    reader = make_reader(db)
    first = issue_book(db, book.id, reader.id, NOW)
    second = issue_book(db, book.id, reader.id, NOW)
    return_book(db, first.id, NOW)

    active = get_active_loans(db, reader.id)

    assert [loan.id for loan in active] == [second.id]


def test_book_with_loan_history_cannot_be_deleted(db):
    book = make_book(db)
    reader = make_reader(db)
    loan = issue_book(db, book.id, reader.id, NOW)
    return_book(db, loan.id, NOW)  # даже возвращённая выдача остаётся в истории

    with pytest.raises(BusinessRuleError):
        ensure_book_has_no_loans(db, book.id)


def test_reader_with_loan_history_cannot_be_deleted(db):
    book = make_book(db)
    reader = make_reader(db)
    issue_book(db, book.id, reader.id, NOW)

    with pytest.raises(BusinessRuleError):
        ensure_reader_has_no_loans(db, reader.id)


def test_book_without_loans_can_be_deleted(db):
    book = make_book(db)

    ensure_book_has_no_loans(db, book.id)  # не должно бросать исключение
