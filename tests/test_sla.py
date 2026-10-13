import pandas as pd
import pytest

from itsm_insights.metrics import sla
from tests.conftest import make_tickets

AS_OF = pd.Timestamp("2026-01-10T00:00:00Z")


def outcome(row: dict, config, as_of=AS_OF) -> tuple[str, str]:
    result = sla.evaluate(make_tickets([row]), config, as_of).iloc[0]
    return result["response_status"], result["resolve_status"]


# Default P1 targets: response 15m, resolve 4h.


def test_met(config):
    row = {
        "created": "2026-01-05T09:00Z",
        "first_response": "2026-01-05T09:10Z",
        "resolved": "2026-01-05T12:00Z",
    }
    assert outcome(row, config) == (sla.MET, sla.MET)


def test_breached(config):
    row = {
        "created": "2026-01-05T09:00Z",
        "first_response": "2026-01-05T09:16Z",
        "resolved": "2026-01-05T13:01Z",
    }
    assert outcome(row, config) == (sla.BREACHED, sla.BREACHED)


def test_exactly_on_target_is_met(config):
    row = {
        "created": "2026-01-05T09:00Z",
        "first_response": "2026-01-05T09:15Z",
        "resolved": "2026-01-05T13:00Z",
    }
    assert outcome(row, config) == (sla.MET, sla.MET)


def test_one_second_over_is_breached(config):
    row = {
        "created": "2026-01-05T09:00:00Z",
        "first_response": "2026-01-05T09:15:01Z",
        "resolved": "2026-01-05T13:00:01Z",
    }
    assert outcome(row, config) == (sla.BREACHED, sla.BREACHED)


def test_24x7_clock_runs_over_the_weekend(config):
    # Friday 18:00 with a 4h target breaches on Friday night under a 24x7 calendar.
    row = {"created": "2026-01-09T18:00Z", "resolved": "2026-01-12T09:00Z"}
    assert outcome(row, config)[1] == sla.BREACHED


def test_open_ticket_within_target_is_pending(config):
    row = {"created": "2026-01-09T23:00Z"}  # 1h old at AS_OF
    assert outcome(row, config) == (sla.BREACHED, sla.PENDING)


def test_open_ticket_past_target_is_breached(config):
    row = {"created": "2026-01-09T12:00Z", "first_response": "2026-01-09T12:05Z"}
    assert outcome(row, config) == (sla.MET, sla.BREACHED)


def test_open_and_unanswered_within_response_target_is_pending(config):
    row = {"created": "2026-01-09T23:50Z"}  # 10 minutes old
    assert outcome(row, config) == (sla.PENDING, sla.PENDING)


def test_resolution_without_response_stops_response_clock(config):
    row = {"created": "2026-01-05T09:00Z", "resolved": "2026-01-05T09:05Z"}
    assert outcome(row, config) == (sla.MET, sla.MET)


def test_priority_without_policy(config):
    row = {"created": "2026-01-05T09:00Z", "priority": "Urgent"}
    assert outcome(row, config) == (sla.NO_POLICY, sla.NO_POLICY)


def test_stop_before_start_is_excluded(config):
    row = {
        "created": "2026-01-05T09:00Z",
        "first_response": "2026-01-05T08:00Z",
        "resolved": "2026-01-05T08:30Z",
    }
    response, resolve = outcome(row, config)
    assert pd.isna(response) and pd.isna(resolve)


def test_naive_as_of_is_treated_as_utc(config):
    row = {"created": "2026-01-09T23:00Z"}
    assert outcome(row, config, as_of=pd.Timestamp("2026-01-10T00:00"))[1] == sla.PENDING


def test_breach_rate_excludes_pending():
    status = pd.Series([sla.MET, sla.MET, sla.BREACHED, sla.PENDING, sla.NO_POLICY, pd.NA])
    summary = sla.summarise(status)
    assert (summary.met, summary.breached, summary.pending) == (2, 1, 1)
    assert summary.rate == pytest.approx(1 / 3)


def test_breach_rate_none_when_nothing_decided():
    assert sla.summarise(pd.Series([sla.PENDING])).rate is None


def test_breach_by_priority(config):
    tickets = make_tickets(
        [
            {"priority": "P1", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T10:00Z"},
            {"priority": "P1", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T15:00Z"},
            {"priority": "P2", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T10:00Z"},
        ]
    )
    rows = sla.breach_by_priority(sla.evaluate(tickets, config, AS_OF), config)
    assert rows["P1"]["tickets"] == 2
    assert rows["P1"]["resolve"].rate == 0.5
    assert rows["P2"]["resolve"].rate == 0.0
    assert rows["P4"]["tickets"] == 0
    assert rows["P4"]["resolve"].rate is None
