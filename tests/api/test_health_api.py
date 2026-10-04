def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_when_database_is_available(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_database_is_down(client):
    """Недоступная база: readiness-проба должна сообщить «не готов», а liveness (/health) остаться зелёной."""
    from sqlalchemy.exc import OperationalError

    from app.database import get_db
    from app.main import app

    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

        def close(self):
            pass

    # фикстура client сама снимет подмену после теста
    app.dependency_overrides[get_db] = lambda: BrokenSession()
    ready = client.get("/ready")
    health = client.get("/health")

    assert ready.status_code == 503
    assert ready.json() == {"status": "database unavailable"}
    assert health.status_code == 200
