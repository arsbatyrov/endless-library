"""Приложение переживает обрыв соединений с базой (перезапуск Postgres, сетевой сбой)."""

from sqlalchemy import text

from app.database import engine as app_engine


def test_app_engine_recovers_after_its_pooled_connection_was_killed(engine):
    """Соединение лежит в пуле, базу «перезапустили» (все соединения оборваны). Следующий запрос приложения
    должен пройти: пул проверяет соединение перед использованием (pool_pre_ping) и открывает новое.

    Без pool_pre_ping этот сценарий давал бы 500 на первом запросе после перезапуска базы."""
    with app_engine.connect() as connection:
        victim_pid = connection.scalar(text("SELECT pg_backend_pid()"))
    # соединение вернулось в пул, но живо; обрываем его со стороны сервера, как при остановке базы
    with engine.begin() as admin:
        admin.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": victim_pid})

    with app_engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1
