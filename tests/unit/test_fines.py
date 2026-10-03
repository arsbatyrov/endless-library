from datetime import datetime, timedelta, timezone

import pytest

from app.services.fines import calculate_fine

DUE = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "delay, expected_fine",
    [
        (timedelta(days=-5), 0),    # вернули раньше срока
        (timedelta(0), 0),          # ровно в срок
        (timedelta(hours=23), 0),   # неполный день не штрафуется
        (timedelta(hours=24), 10),  # ровно один полный день
        (timedelta(hours=47), 10),  # один полный день и почти второй
        (timedelta(days=3), 30),
    ],
)
def test_calculate_fine(delay, expected_fine):
    returned_at = DUE + delay

    assert calculate_fine(DUE, returned_at) == expected_fine
