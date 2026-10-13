"""Working-time calendars: how much SLA-relevant time passed between two instants.

A ticket opened Friday 18:00 with a 4-hour business-hours target is not
breached on Saturday. Working windows are built per day in the calendar's
local timezone and compared in UTC, so days when the clocks change still get
their full opening hours.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd

Interval = tuple[pd.Timestamp, pd.Timestamp]


class Calendar(Protocol):
    name: str

    def working_seconds(self, start: pd.Timestamp, end: pd.Timestamp) -> float: ...

    def add_working_time(self, start: pd.Timestamp, seconds: float) -> pd.Timestamp: ...


def _require_aware(*stamps: pd.Timestamp) -> None:
    for ts in stamps:
        if ts.tzinfo is None:
            raise ValueError("calendar arithmetic needs timezone-aware timestamps")


@dataclass(frozen=True)
class TwentyFourSeven:
    """Every second counts."""

    name: str = "24x7"

    def working_seconds(self, start: pd.Timestamp, end: pd.Timestamp) -> float:
        _require_aware(start, end)
        return max((end - start).total_seconds(), 0.0)

    def add_working_time(self, start: pd.Timestamp, seconds: float) -> pd.Timestamp:
        _require_aware(start)
        return start + pd.Timedelta(seconds=seconds)


TWENTY_FOUR_SEVEN = TwentyFourSeven()


@dataclass(frozen=True)
class BusinessCalendar:
    """Opening hours on given weekdays (Mon=0), minus holidays, in a local timezone.

    Windows must open and close on the same day; overnight shifts are not supported.
    """

    name: str
    timezone: str
    workdays: frozenset[int]
    opens: time
    closes: time
    holidays: frozenset[date] = frozenset()
    _windows: dict = field(default_factory=dict, compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        if self.closes <= self.opens:
            raise ValueError(
                f"calendar {self.name!r}: hours must close after they open "
                f"({self.opens:%H:%M}-{self.closes:%H:%M}); overnight windows are not supported"
            )
        if not self.workdays:
            raise ValueError(f"calendar {self.name!r} needs at least one working day")
        ZoneInfo(self.timezone)  # fail early on unknown zones

    def _window(self, day: date) -> Interval | None:
        if day in self._windows:
            return self._windows[day]
        window = None
        if day.weekday() in self.workdays and day not in self.holidays:
            window = (self._local(day, self.opens), self._local(day, self.closes))
        self._windows[day] = window
        return window

    def _local(self, day: date, at: time) -> pd.Timestamp:
        naive = pd.Timestamp(datetime.combine(day, at))
        local = naive.tz_localize(self.timezone, ambiguous=True, nonexistent="shift_forward")
        return local.tz_convert("UTC")

    def _local_date(self, ts: pd.Timestamp) -> date:
        return ts.tz_convert(self.timezone).date()

    def working_seconds(self, start: pd.Timestamp, end: pd.Timestamp) -> float:
        _require_aware(start, end)
        if end <= start:
            return 0.0
        total = 0.0
        day, last = self._local_date(start), self._local_date(end)
        while day <= last:
            window = self._window(day)
            if window:
                lo, hi = max(start, window[0]), min(end, window[1])
                if hi > lo:
                    total += (hi - lo).total_seconds()
            day += timedelta(days=1)
        return total

    def add_working_time(self, start: pd.Timestamp, seconds: float) -> pd.Timestamp:
        """The instant when ``seconds`` of working time have passed since ``start``.

        With ``seconds == 0`` and ``start`` outside working hours, this is the next
        opening time: the moment the clock would start running.
        """
        _require_aware(start)
        if seconds < 0:
            raise ValueError("seconds must not be negative")
        remaining = float(seconds)
        day = self._local_date(start)
        for _ in range(366 * 20):
            window = self._window(day)
            if window:
                lo = max(start, window[0])
                if lo < window[1]:
                    available = (window[1] - lo).total_seconds()
                    if remaining <= available:
                        return lo + pd.Timedelta(seconds=remaining)
                    remaining -= available
            day += timedelta(days=1)
        raise ValueError(f"calendar {self.name!r} has no working time within 20 years")


def merge_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for lo, hi in sorted((lo, hi) for lo, hi in intervals if hi > lo):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def active_seconds(
    start: pd.Timestamp,
    end: pd.Timestamp,
    calendar: Calendar,
    pauses: Iterable[Interval] = (),
) -> float:
    """Working time from ``start`` to ``end`` that is not inside a pause.

    Pauses are clipped to [start, end] and merged first, so overlapping or
    out-of-range intervals are safe.
    """
    if end <= start:
        return 0.0
    total = calendar.working_seconds(start, end)
    for lo, hi in merge_intervals((max(lo, start), min(hi, end)) for lo, hi in pauses):
        total -= calendar.working_seconds(lo, hi)
    return max(total, 0.0)
