from datetime import datetime

FINE_PER_DAY = 10


def calculate_fine(due_at: datetime, returned_at: datetime) -> int:
    """Штраф за просрочку: FINE_PER_DAY за каждый ПОЛНЫЙ день после срока."""
    overdue_days = (returned_at - due_at).days
    return max(overdue_days, 0) * FINE_PER_DAY
