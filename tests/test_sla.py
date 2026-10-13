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


# --- v0.2: business-hours calendars and clock pausing ---

BUSINESS = {"days": ["mon-fri"], "hours": "09:00-17:00"}


def business_config(**sla_overrides):
    from itsm_insights.config import Config, SLAPolicy

    sla = {
        "P1": SLAPolicy(response="15m", resolve="4h", calendar="business"),
        "P2": SLAPolicy(response="1h", resolve="8h"),  # 24x7
    }
    sla.update(sla_overrides)
    return Config(timezone="UTC", calendars={"business": BUSINESS}, sla=sla)


def evaluate_one(row, config, pauses=None, as_of=AS_OF):
    tickets = make_tickets([{"id": "T", **row}])
    return sla.evaluate(tickets, config, as_of, pauses=pauses).iloc[0]


def test_friday_evening_ticket_does_not_breach_over_the_weekend():
    row = {"created": "2026-01-09T18:00Z", "resolved": "2026-01-12T12:00Z"}
    result = evaluate_one(row, business_config(), as_of=pd.Timestamp("2026-01-13T00:00Z"))
    assert result["resolve_elapsed"] == pd.Timedelta(hours=3)
    assert result["resolve_status"] == sla.MET
    assert result["calendar"] == "business"


def test_same_ticket_breaches_on_a_24x7_clock():
    row = {"priority": "P2", "created": "2026-01-09T18:00Z", "resolved": "2026-01-12T12:00Z"}
    result = evaluate_one(row, business_config(), as_of=pd.Timestamp("2026-01-13T00:00Z"))
    assert result["resolve_status"] == sla.BREACHED
    assert result["calendar"] == "24x7"


def test_saturday_ticket_answered_monday_morning():
    row = {"created": "2026-01-10T10:00Z", "first_response": "2026-01-12T09:10Z"}
    result = evaluate_one(row, business_config(), as_of=pd.Timestamp("2026-01-12T10:00Z"))
    assert result["response_elapsed"] == pd.Timedelta(minutes=10)
    assert result["response_status"] == sla.MET


def ts(text):
    return pd.Timestamp(text, tz="UTC")


def test_pause_is_subtracted_from_resolution():
    row = {"priority": "P2", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T15:00Z"}
    pauses = {"T": [(ts("2026-01-05T10:00"), ts("2026-01-05T13:00"))]}
    result = evaluate_one(row, business_config(), pauses=pauses)
    assert result["resolve_elapsed"] == pd.Timedelta(hours=3)


def test_pause_does_not_shorten_the_response_clock():
    row = {
        "created": "2026-01-05T09:00Z",
        "first_response": "2026-01-05T09:30Z",
        "resolved": "2026-01-05T10:00Z",
    }
    pauses = {"T": [(ts("2026-01-05T09:05"), ts("2026-01-05T09:40"))]}
    result = evaluate_one(row, business_config(), pauses=pauses)
    assert result["response_elapsed"] == pd.Timedelta(minutes=30)
    assert result["response_status"] == sla.BREACHED


def test_ticket_waiting_on_the_customer_at_as_of_is_pending():
    row = {"priority": "P2", "created": "2026-01-05T09:00Z", "first_response": "2026-01-05T09:10Z"}
    pauses = {"T": [(ts("2026-01-05T09:30"), AS_OF)]}
    result = evaluate_one(row, business_config(), pauses=pauses)
    assert result["resolve_elapsed"] == pd.Timedelta(minutes=30)
    assert result["resolve_status"] == sla.PENDING


def test_pause_before_creation_is_clipped():
    row = {"priority": "P2", "created": "2026-01-05T09:00Z", "resolved": "2026-01-05T14:00Z"}
    pauses = {"T": [(ts("2026-01-05T08:00"), ts("2026-01-05T10:00"))]}
    result = evaluate_one(row, business_config(), pauses=pauses)
    assert result["resolve_elapsed"] == pd.Timedelta(hours=4)
    assert result["resolve_status"] == sla.MET  # 4h against an 8h target


def test_open_business_ticket_measured_in_working_time():
    # Created Friday 16:00; at Monday 10:00 only 2 working hours have passed (< 4h): pending.
    row = {"created": "2026-01-09T16:00Z", "first_response": "2026-01-09T16:05Z"}
    result = evaluate_one(row, business_config(), as_of=pd.Timestamp("2026-01-12T10:00Z"))
    assert result["resolve_elapsed"] == pd.Timedelta(hours=2)
    assert result["resolve_status"] == sla.PENDING
