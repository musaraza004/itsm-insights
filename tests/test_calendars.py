from datetime import date, time

import pandas as pd
import pytest

from itsm_insights.calendars import (
    TWENTY_FOUR_SEVEN,
    BusinessCalendar,
    active_seconds,
)

H = 3600.0


def ts(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz="UTC")


@pytest.fixture
def cal() -> BusinessCalendar:
    # Europe/London is UTC in January, so local and UTC times match in most tests.
    return BusinessCalendar(
        name="business",
        timezone="Europe/London",
        workdays=frozenset(range(5)),
        opens=time(9),
        closes=time(17),
        holidays=frozenset({date(2026, 12, 25)}),
    )


def test_same_day(cal):
    assert cal.working_seconds(ts("2026-01-05T10:00"), ts("2026-01-05T12:00")) == 2 * H


def test_clips_to_opening_hours(cal):
    assert cal.working_seconds(ts("2026-01-05T07:00"), ts("2026-01-05T20:00")) == 8 * H


def test_friday_evening_to_monday(cal):
    # Fri 9 Jan 16:00 -> Mon 12 Jan 10:00: 1h Friday + 1h Monday.
    assert cal.working_seconds(ts("2026-01-09T16:00"), ts("2026-01-12T10:00")) == 2 * H


def test_weekend_is_zero(cal):
    assert cal.working_seconds(ts("2026-01-10T10:00"), ts("2026-01-11T18:00")) == 0


def test_saturday_ticket_answered_monday_morning(cal):
    assert cal.working_seconds(ts("2026-01-10T10:00"), ts("2026-01-12T09:10")) == 10 * 60


def test_end_before_start_is_zero(cal):
    assert cal.working_seconds(ts("2026-01-05T12:00"), ts("2026-01-05T10:00")) == 0


def test_holiday_is_skipped(cal):
    # Thu 24 Dec 16:00 -> Mon 28 Dec 10:00; Fri 25 Dec is a holiday.
    assert cal.working_seconds(ts("2026-12-24T16:00"), ts("2026-12-28T10:00")) == 2 * H


def test_two_weeks(cal):
    assert cal.working_seconds(ts("2026-01-05T09:00"), ts("2026-01-19T09:00")) == 80 * H


def test_daylight_saving_day_uses_local_hours():
    # Clocks go forward on Sunday 29 March 2026; 09:00-17:00 BST is still 8 hours.
    every_day = BusinessCalendar("all", "Europe/London", frozenset(range(7)), time(9), time(17))
    start, end = ts("2026-03-29T00:00"), ts("2026-03-30T00:00")
    assert every_day.working_seconds(start, end) == 8 * H
    # And the window sits at 08:00-16:00 UTC that day.
    assert every_day.working_seconds(ts("2026-03-29T08:00"), ts("2026-03-29T09:00")) == H


def test_add_working_time_rolls_over_the_weekend(cal):
    assert cal.add_working_time(ts("2026-01-09T16:00"), 4 * H) == ts("2026-01-12T12:00")


def test_add_zero_from_saturday_is_monday_opening(cal):
    assert cal.add_working_time(ts("2026-01-10T10:00"), 0) == ts("2026-01-12T09:00")


@pytest.mark.parametrize("start", ["2026-01-05T08:00", "2026-01-07T16:59", "2026-01-10T03:00"])
@pytest.mark.parametrize("hours", [0.25, 3, 8, 30, 100])
def test_add_then_measure_round_trip(cal, start, hours):
    end = cal.add_working_time(ts(start), hours * H)
    assert cal.working_seconds(ts(start), end) == pytest.approx(hours * H)


def test_invalid_calendars():
    with pytest.raises(ValueError, match="close after"):
        BusinessCalendar("x", "UTC", frozenset({0}), time(17), time(9))
    with pytest.raises(ValueError, match="at least one working day"):
        BusinessCalendar("x", "UTC", frozenset(), time(9), time(17))


def test_naive_timestamps_rejected(cal):
    with pytest.raises(ValueError, match="timezone-aware"):
        cal.working_seconds(pd.Timestamp("2026-01-05T10:00"), ts("2026-01-05T12:00"))


def test_twenty_four_seven():
    assert (
        TWENTY_FOUR_SEVEN.working_seconds(ts("2026-01-10T10:00"), ts("2026-01-10T12:00")) == 2 * H
    )
    assert TWENTY_FOUR_SEVEN.add_working_time(ts("2026-01-10T10:00"), H) == ts("2026-01-10T11:00")


def test_active_seconds_subtracts_only_working_pause_time(cal):
    start, end = ts("2026-01-05T09:00"), ts("2026-01-05T17:00")
    # Paused 12:00-20:00: only 12:00-17:00 is working time, leaving 3h.
    assert (
        active_seconds(start, end, cal, [(ts("2026-01-05T12:00"), ts("2026-01-05T20:00"))]) == 3 * H
    )


def test_active_seconds_clips_pauses_to_the_clock(cal):
    start, end = ts("2026-01-05T10:00"), ts("2026-01-05T14:00")
    pauses = [
        (ts("2026-01-05T08:00"), ts("2026-01-05T11:00")),
        (ts("2026-01-06T09:00"), ts("2026-01-06T10:00")),
    ]
    assert active_seconds(start, end, cal, pauses) == 3 * H


def test_active_seconds_merges_overlapping_pauses():
    start, end = ts("2026-01-05T00:00"), ts("2026-01-05T10:00")
    pauses = [
        (ts("2026-01-05T01:00"), ts("2026-01-05T04:00")),
        (ts("2026-01-05T03:00"), ts("2026-01-05T05:00")),
    ]
    assert active_seconds(start, end, TWENTY_FOUR_SEVEN, pauses) == 6 * H
