import pandas as pd
import pytest

from itsm_insights.metrics.handling import Rate, escalation_rate, fcr, reopen_rate
from tests.conftest import make_tickets


@pytest.fixture
def tickets():
    return make_tickets(
        [
            {"id": "A", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T10:00Z"},  # FCR
            {
                "id": "B",
                "created": "2026-01-05T09:00Z",
                "resolved": "2026-01-05T10:00Z",
            },  # reopened
            {
                "id": "C",
                "created": "2026-01-05T09:00Z",
                "resolved": "2026-01-05T10:00Z",
            },  # escalated
            {
                "id": "D",
                "created": "2026-01-05T09:00Z",
                "resolved": "2026-01-05T10:00Z",
            },  # reassigned
            {"id": "E", "created": "2026-01-05T09:00Z"},  # open, escalated
            {
                "id": "F",
                "created": "2026-01-05T09:00Z",
                "resolved": "2026-01-05T10:00Z",
            },  # no history
        ]
    )


@pytest.fixture
def facts():
    return pd.DataFrame(
        {
            "has_history": [True, True, True, True, True, False],
            "reopens": [0, 1, 0, 0, 0, 0],
            "escalations": [0, 0, 1, 0, 1, 0],
            "reassignments": [0, 0, 1, 1, 1, 0],
        },
        index=pd.Index(list("ABCDEF"), name="id"),
    )


def test_fcr_counts_resolved_tickets_handled_once(tickets, facts):
    # Resolved with history: A, B, C, D. Only A was never reopened, escalated or reassigned.
    assert fcr(tickets, facts) == Rate(1, 4)


def test_reopen_rate_over_tickets_resolved_at_least_once(tickets, facts):
    assert reopen_rate(tickets, facts) == Rate(1, 4)


def test_escalation_rate_over_all_tickets_with_history(facts):
    assert escalation_rate(facts) == Rate(2, 5)


def test_rate_properties():
    assert Rate(1, 4).rate == 0.25
    assert Rate(0, 0).rate is None
    assert Rate(1, 4).as_dict() == {"count": 1, "of": 4, "rate": 0.25}


def test_reopened_but_currently_open_counts_as_resolved_once(facts):
    tickets = make_tickets([{"id": "B", "created": "2026-01-05T09:00Z"}])
    one = facts.loc[["B"]]
    assert reopen_rate(tickets, one) == Rate(1, 1)
    assert fcr(tickets, one) == Rate(0, 0)
