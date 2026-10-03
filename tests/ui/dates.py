from datetime import UTC, datetime


def ru_date(iso: str) -> str:
    """Дата в том виде, как её показывает интерфейс: дд.мм.гггг в UTC."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC).strftime("%d.%m.%Y")
