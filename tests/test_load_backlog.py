import pandas as pd

from itsm_insights.config import ColumnMap, Config
from itsm_insights.loaders import check_mapping
from itsm_insights.metrics import backlog, load
from tests.conftest import make_tickets

AS_OF = pd.Timestamp("2026-01-20T12:00:00Z")


def test_heatmap_counts_in_local_time():
    tickets = make_tickets(
        [
            {"created": "2026-01-05T09:30Z"},  # Monday 09:30 UTC
            {"created": "2026-01-05T09:59Z"},
            {"created": "2026-07-06T09:30Z"},  # Monday 10:30 in London (BST)
            {"created": "2026-01-11T23:30Z"},  # Sunday 23:30
        ]
    )
    grid = load.weekday_hour_counts(tickets, "Europe/London")
    assert len(grid) == 7 and all(len(row) == 24 for row in grid)
    assert grid[0][9] == 2
    assert grid[0][10] == 1
    assert grid[6][23] == 1
    assert sum(map(sum, grid)) == 4


def test_peak_prefers_earliest_on_tie():
    grid = [[0] * 24 for _ in range(7)]
    grid[2][14] = 5
    grid[1][10] = 5
    assert load.peak(grid) == {"weekday": "Tue", "hour": 10, "tickets": 5}


def test_backlog_buckets_boundaries():
    def created(days_ago: float) -> str:
        return (AS_OF - pd.Timedelta(days=days_ago)).isoformat()

    tickets = make_tickets(
        [
            {"created": created(0.5)},
            {"created": created(1.0)},  # exactly 1 day -> 1-3d
            {"created": created(2.9)},
            {"created": created(3.0)},  # 3-7d
            {"created": created(7.0)},  # 7d+
            {"created": created(30)},
            {"created": created(2), "resolved": created(1)},  # resolved: not backlog
            {"created": (AS_OF + pd.Timedelta(hours=1)).isoformat()},  # future: skipped
        ]
    )
    assert backlog.ageing(tickets, AS_OF) == {"0-1d": 1, "1-3d": 2, "3-7d": 1, "7d+": 2}


def test_backlog_empty_when_all_resolved():
    tickets = make_tickets([{"created": "2026-01-05T09:00Z", "resolved": "2026-01-05T10:00Z"}])
    assert backlog.ageing(tickets, AS_OF) == {"0-1d": 0, "1-3d": 0, "3-7d": 0, "7d+": 0}


def test_check_mapping_reports_found_and_missing(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text("Key,Opened,Priority,Done\nA,2026-01-01,P1,\n", encoding="utf-8")
    cfg = Config(
        columns=ColumnMap(id="Key", created="Opened", priority="Priority", resolved="Done")
    )
    result = {row["field"]: row for row in check_mapping(path, cfg)}
    assert result["id"] == {
        "field": "id",
        "column": "Key",
        "configured": "Key",
        "required": True,
        "found": True,
        "auto": False,
    }
    assert result["resolved"]["found"] is True
    assert result["first_response"]["found"] is False
    assert result["first_response"]["required"] is False
