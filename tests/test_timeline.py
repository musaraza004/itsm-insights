import pandas as pd

from itsm_insights.config import Config
from itsm_insights.timeline import escalation_paths, pause_intervals, ticket_facts
from tests.conftest import make_tickets

AS_OF = pd.Timestamp("2026-01-10T00:00Z")
CFG = Config(
    pause_statuses=["Waiting for customer", "Pending vendor"],
    escalation_tiers=["L1", "L2", "Vendor"],
)


def ts(text):
    return pd.Timestamp(text, tz="UTC")


def make_history(rows):
    """rows: (id, 'YYYY-MM-DDTHH:MM', field, value)."""
    df = pd.DataFrame(rows, columns=["id", "at", "field", "value"])
    df["at"] = pd.to_datetime(df["at"], utc=True)
    for col in ("id", "field", "value"):
        df[col] = df[col].astype("string")
    return df.sort_values(["id", "at"], kind="stable").reset_index(drop=True)


def test_waiting_period_becomes_a_pause():
    h = make_history(
        [
            ("T1", "2026-01-05T09:00", "status", "Open"),
            ("T1", "2026-01-05T10:00", "status", "Waiting for customer"),
            ("T1", "2026-01-05T12:00", "status", "In Progress"),
        ]
    )
    assert pause_intervals(h, CFG, AS_OF) == {
        "T1": [(ts("2026-01-05T10:00"), ts("2026-01-05T12:00"))]
    }


def test_still_waiting_runs_to_as_of():
    h = make_history([("T1", "2026-01-05T10:00", "status", "waiting FOR customer")])
    assert pause_intervals(h, CFG, AS_OF) == {"T1": [(ts("2026-01-05T10:00"), AS_OF)]}


def test_consecutive_pausing_statuses_merge():
    h = make_history(
        [
            ("T1", "2026-01-05T10:00", "status", "Waiting for customer"),
            ("T1", "2026-01-05T11:00", "status", "Pending vendor"),
            ("T1", "2026-01-05T13:00", "status", "In Progress"),
        ]
    )
    assert pause_intervals(h, CFG, AS_OF)["T1"] == [
        (ts("2026-01-05T10:00"), ts("2026-01-05T13:00"))
    ]


def test_time_spent_resolved_before_a_reopen_is_paused():
    h = make_history(
        [
            ("T1", "2026-01-05T09:00", "status", "In Progress"),
            ("T1", "2026-01-05T10:00", "status", "Resolved"),
            ("T1", "2026-01-06T10:00", "status", "In Progress"),
            ("T1", "2026-01-06T11:00", "status", "Resolved (fixed)"),
        ]
    )
    pauses = pause_intervals(h, CFG, AS_OF)["T1"]
    assert pauses[0] == (ts("2026-01-05T10:00"), ts("2026-01-06T10:00"))


def test_assignment_events_do_not_create_pauses():
    h = make_history([("T1", "2026-01-05T10:00", "assignee_group", "Waiting for customer")])
    assert pause_intervals(h, CFG, AS_OF) == {}


def test_ticket_facts():
    tickets = make_tickets(
        [
            {"id": "T1", "created": "2026-01-05T09:00Z", "resolved": "2026-01-06T11:00Z"},
            {"id": "T2", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T12:00Z"},
            {"id": "T3", "created": "2026-01-05T09:00Z"},
            {"id": "T4", "created": "2026-01-05T09:00Z"},  # no history
        ]
    )
    h = make_history(
        [
            # T1: reopened once, escalated L1 -> L2 -> Vendor, assignee changed twice.
            ("T1", "2026-01-05T09:00", "status", "Open"),
            ("T1", "2026-01-05T09:00", "assignee_group", "L1"),
            ("T1", "2026-01-05T09:05", "assignee", "Ann"),
            ("T1", "2026-01-05T10:00", "assignee_group", "L2"),
            ("T1", "2026-01-05T10:00", "assignee", "Bo"),
            ("T1", "2026-01-05T11:00", "status", "Resolved"),
            ("T1", "2026-01-05T15:00", "status", "In Progress"),
            ("T1", "2026-01-05T16:00", "assignee_group", "Vendor"),
            ("T1", "2026-01-06T11:00", "status", "Resolved"),
            ("T1", "2026-01-07T11:00", "status", "Closed"),  # resolved -> closed is not a reopen
            # T2: lateral move to an unknown group, then back down: reassignments only.
            ("T2", "2026-01-05T09:00", "assignee_group", "L2"),
            ("T2", "2026-01-05T09:30", "assignee_group", "Desktop"),
            ("T2", "2026-01-05T10:00", "assignee_group", "L1"),
            ("T2", "2026-01-05T12:00", "status", "Resolved"),
            # T3: same group recorded twice is not a change.
            ("T3", "2026-01-05T09:00", "assignee_group", "L1"),
            ("T3", "2026-01-05T09:10", "assignee_group", "L1"),
            # Unknown ticket: ignored.
            ("ZZ", "2026-01-05T09:00", "status", "Resolved"),
        ]
    )
    facts = ticket_facts(tickets, h, CFG)
    assert list(facts.index) == ["T1", "T2", "T3", "T4"]
    assert facts.loc["T1"].to_dict() == {
        "has_history": True,
        "reopens": 1,
        "escalations": 2,
        "reassignments": 3,
    }
    assert facts.loc["T2", "escalations"] == 0 and facts.loc["T2", "reassignments"] == 2
    assert facts.loc["T3", "reassignments"] == 0
    assert not facts.loc["T4", "has_history"]


def test_escalation_paths():
    h = make_history(
        [
            ("T1", "2026-01-05T09:00", "assignee_group", "L1"),
            ("T1", "2026-01-05T10:00", "assignee_group", "L2"),
            ("T2", "2026-01-05T09:00", "assignee_group", "l1"),
            ("T2", "2026-01-05T10:00", "assignee_group", "L2"),
            ("T2", "2026-01-05T11:00", "assignee_group", "Vendor"),
            ("T3", "2026-01-05T09:00", "assignee_group", "L2"),
            ("T3", "2026-01-05T10:00", "assignee_group", "L1"),
        ]
    )
    assert escalation_paths(h, CFG) == {"L1 -> L2": 2, "L2 -> Vendor": 1}


def test_no_tiers_means_no_escalations():
    h = make_history(
        [
            ("T1", "2026-01-05T09:00", "assignee_group", "L1"),
            ("T1", "2026-01-05T10:00", "assignee_group", "L2"),
        ]
    )
    assert escalation_paths(h, Config()) == {}
