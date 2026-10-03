"""Гонки: два запроса одновременно меняют одни и те же данные.

Как воспроизвести гонку стабильно, а не «раз из ста»: два потока выполняют действие
параллельно (у каждого своя сессия, то есть своё соединение с базой), а «барьер»,
вставленный в середину функции сервиса, заставляет оба потока дойти до одной точки
раньше, чем любой из них запишет результат. Так мы получаем самое неудачное
чередование шагов, которое в жизни случается редко и непредсказуемо.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Book, Loan
from app.services import loans as loan_service
from app.services.errors import BusinessRuleError
from tests.factories import make_book, make_reader

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def meet_in_the_middle_of(monkeypatch, function_name: str, timeout: float = 1.0) -> None:
    """Оба потока, дойдя до вызова `function_name` внутри сервиса, ждут друг друга.

    Если один поток заблокирован базой (ждёт блокировку строки) и до барьера не дойдёт,
    второй не ждёт вечно: по таймауту барьер «ломается» и поток идёт дальше. Благодаря
    этому тест корректно работает и с блокировками, и без них.
    """
    original = getattr(loan_service, function_name)
    barrier = threading.Barrier(2)

    def wrapper(*args, **kwargs):
        try:
            barrier.wait(timeout=timeout)
        except threading.BrokenBarrierError:
            pass
        return original(*args, **kwargs)

    monkeypatch.setattr(loan_service, function_name, wrapper)


def run_in_parallel(engine, *actions) -> list[str]:
    """Выполняет каждое действие в своём потоке и со своей сессией. Результат: 'ok' или 'refused'."""

    def run(action) -> str:
        with Session(engine, autoflush=False) as session:
            try:
                action(session)
                return "ok"
            except BusinessRuleError:
                return "refused"

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        futures = [pool.submit(run, action) for action in actions]
        return [future.result(timeout=15) for future in futures]


def test_two_readers_racing_for_the_last_copy_only_one_gets_it(engine, db, monkeypatch):
    book = make_book(db, copies=1)
    first, second = make_reader(db), make_reader(db)
    book_id, first_id, second_id = book.id, first.id, second.id  # id берём до запуска потоков
    meet_in_the_middle_of(monkeypatch, "count_active_loans")

    outcomes = run_in_parallel(
        engine,
        lambda session: loan_service.issue_book(session, book_id, first_id, NOW),
        lambda session: loan_service.issue_book(session, book_id, second_id, NOW),
    )

    assert sorted(outcomes) == ["ok", "refused"]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Loan)) == 1
    assert db.get(Book, book_id).copies_available == 0


def test_two_simultaneous_returns_of_the_same_loan_succeed_only_once(engine, db, monkeypatch):
    book = make_book(db, copies=1)
    reader = make_reader(db)
    loan = loan_service.issue_book(db, book.id, reader.id, NOW)
    book_id, loan_id = book.id, loan.id
    meet_in_the_middle_of(monkeypatch, "calculate_fine")

    outcomes = run_in_parallel(
        engine,
        lambda session: loan_service.return_book(session, loan_id, NOW + timedelta(days=1)),
        lambda session: loan_service.return_book(session, loan_id, NOW + timedelta(days=1)),
    )

    assert sorted(outcomes) == ["ok", "refused"]
    db.expire_all()
    assert db.get(Book, book_id).copies_available == 1
