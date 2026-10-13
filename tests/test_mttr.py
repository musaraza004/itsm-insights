import pandas as pd

from itsm_insights.metrics import mttr
from tests.conftest import make_tickets


def tickets_resolving_in(hours: list[float | None], priority: str = "P3") -> pd.DataFrame:
    start = pd.Timestamp("2026-01-05T09:00Z")
    rows = []
    for h in hours:
        resolved = None if h is None else (start + pd.Timedelta(hours=h)).isoformat()
        rows.append({"created": start.isoformat(), "resolved": resolved, "priority": priority})
    return make_tickets(rows)


def test_mean_median_p90():
    stats = mttr.mttr(tickets_resolving_in([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
    assert stats.count == 10
    assert stats.mean == pd.Timedelta(hours=5.5)
    assert stats.median == pd.Timedelta(hours=5.5)
    # Linear interpolation: rank 0.9 * 9 = 8.1 -> 9h + 0.1 * 1h.
    assert stats.p90 == pd.Timedelta(hours=9.1)


def test_outlier_moves_mean_not_median():
    stats = mttr.mttr(tickets_resolving_in([1, 1, 1, 1, 200]))
    assert stats.median == pd.Timedelta(hours=1)
    assert stats.mean == pd.Timedelta(hours=40.8)


def test_open_tickets_excluded():
    stats = mttr.mttr(tickets_resolving_in([2, None, 4]))
    assert stats.count == 2
    assert stats.mean == pd.Timedelta(hours=3)


def test_resolved_before_created_excluded():
    stats = mttr.mttr(tickets_resolving_in([-1, 2]))
    assert stats.count == 1
    assert stats.median == pd.Timedelta(hours=2)


def test_no_resolved_tickets():
    stats = mttr.mttr(tickets_resolving_in([None, None]))
    assert stats.count == 0
    assert stats.mean is None
    assert stats.as_dict()["p90_seconds"] is None


def test_by_priority_natural_order():
    tickets = pd.concat(
        [
            tickets_resolving_in([10], "P10"),
            tickets_resolving_in([2], "P2"),
            tickets_resolving_in([1], "P1"),
        ],
        ignore_index=True,
    )
    result = mttr.mttr_by(tickets, "priority")
    assert list(result) == ["P1", "P2", "P10"]
    assert result["P2"].mean == pd.Timedelta(hours=2)
