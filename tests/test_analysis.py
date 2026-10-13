import pandas as pd
import pytest

from itsm_insights.analysis import analyze, default_as_of
from itsm_insights.config import Config
from itsm_insights.loaders import load_tickets
from tests.conftest import make_tickets


@pytest.fixture
def tickets():
    return make_tickets(
        [
            {"created": "2026-01-05T09:00Z", "resolved": "2026-01-05T10:00Z"},
            {"created": "2026-01-05T09:00Z", "resolved": "2026-01-05T18:00Z"},
            {"created": "2026-01-06T09:00Z", "first_response": "2026-01-06T09:05Z"},
        ]
    )


def test_default_as_of_is_latest_timestamp(tickets):
    assert default_as_of(tickets) == pd.Timestamp("2026-01-06T09:05Z")


def test_counts_and_rates(tickets):
    result = analyze(tickets, Config())
    assert (result.total, result.resolved, result.open) == (3, 2, 1)
    # Open ticket is 5 minutes old at the default as-of: pending, not counted.
    assert (result.resolve.met, result.resolve.breached, result.resolve.pending) == (1, 1, 1)
    assert result.resolve.rate == 0.5
    assert result.warnings == []


def test_naive_as_of_uses_config_timezone(tickets):
    result = analyze(tickets, Config(timezone="Europe/London"), as_of=pd.Timestamp("2026-01-07"))
    assert result.as_of == pd.Timestamp("2026-01-07T00:00Z")  # GMT in January
    assert result.resolve.breached == 2  # open ticket is now well past 4h


def test_as_dict_is_json_ready(tickets):
    data = analyze(tickets, Config()).as_dict()
    assert data["tickets"] == {"total": 3, "resolved": 2, "open": 1}
    assert data["sla"]["by_priority"]["P1"]["resolve"]["breach_rate"] == 0.5
    assert data["time_to_resolve"]["overall"]["median_seconds"] == 5 * 3600


def test_warnings_for_bad_data():
    tickets = make_tickets(
        [
            {"created": "2026-01-05T09:00Z", "priority": "Urgent"},
            {
                "created": "2026-01-05T09:00Z",
                "first_response": "2026-01-05T08:00Z",
                "resolved": "2026-01-05T08:30Z",
            },
            {"created": "2026-02-01T00:00Z"},
        ]
    )
    cfg = Config(pause_statuses=["Waiting for customer"])
    warnings = analyze(tickets, cfg, as_of=pd.Timestamp("2026-01-10T00:00Z")).warnings
    text = "\n".join(warnings)
    assert "priority with no SLA" in text and "Urgent" in text
    assert "first response before creation" in text
    assert "resolved before creation" in text
    assert "created after the analysis time" in text
    assert "pause_statuses" in text


def test_header_only_export_rejected(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("ticket_id,created_at,priority\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no tickets"):
        analyze(load_tickets(path, Config()), Config())


def _history(rows):
    df = pd.DataFrame(rows, columns=["id", "at", "field", "value"])
    df["at"] = pd.to_datetime(df["at"], utc=True)
    for col in ("id", "field", "value"):
        df[col] = df[col].astype("string")
    return df


def test_history_drives_pauses_and_handling_rates():
    tickets = make_tickets(
        [
            {"id": "T1", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T15:00Z"},
            {"id": "T2", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T10:00Z"},
            {"id": "T3", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T10:00Z"},
        ]
    )
    history = _history(
        [
            ("T1", "2026-01-05T09:00", "assignee_group", "L1"),
            ("T1", "2026-01-05T10:00", "status", "Waiting for customer"),
            ("T1", "2026-01-05T13:00", "status", "In Progress"),
            ("T1", "2026-01-05T15:00", "status", "Resolved"),
            ("T2", "2026-01-05T09:00", "assignee_group", "L1"),
            ("T2", "2026-01-05T09:30", "assignee_group", "L2"),
            ("T2", "2026-01-05T10:00", "status", "Resolved"),
            ("XX", "2026-01-05T10:00", "status", "Resolved"),
        ]
    )
    cfg = Config(pause_statuses=["Waiting for customer"], escalation_tiers=["L1", "L2"])
    result = analyze(tickets, cfg, as_of=pd.Timestamp("2026-01-06T00:00Z"), history=history)
    # T1: 6h wall clock, 3h paused -> 3h, inside the 4h P1 target.
    assert result.resolve.met == 3 and result.resolve.breached == 0
    data = result.as_dict()
    handling = data["handling"]
    assert handling["fcr"] == {"count": 1, "of": 2, "rate": 0.5}  # T1 clean, T2 escalated
    assert handling["escalation"]["count"] == 1
    assert handling["escalation_paths"] == {"L1 -> L2": 1}
    assert data["sla"]["calendars"] == {"P1": "24x7", "P2": "24x7", "P3": "24x7", "P4": "24x7"}
    text = " ".join(result.warnings)
    assert "1 ticket(s) have no history" in text  # T3
    assert "1 ticket id(s) in the history are not in the ticket export" in text


def test_without_history_handling_is_null_and_pause_warning_explains():
    tickets = make_tickets([{"created": "2026-01-05T09:00Z", "resolved": "2026-01-05T10:00Z"}])
    result = analyze(tickets, Config(pause_statuses=["Waiting for customer"]))
    assert result.as_dict()["handling"] is None
    assert any("no history file" in w for w in result.warnings)
