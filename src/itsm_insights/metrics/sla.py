"""SLA breach calculation on working-time calendars, with clock pausing.

Elapsed time is measured on the calendar named by each priority's policy
(``24x7`` or a business-hours calendar). The resolution clock also stops
while the ticket is in a pausing status (see ``timeline.pause_intervals``);
the response clock never pauses, since waiting on a customer cannot happen
before anyone has answered.

Each ticket gets a response outcome and a resolution outcome:

* ``met``       the clock stopped within the target (exactly on target counts as met)
* ``breached``  the clock stopped after the target, or is still running and has
                already passed it as of the analysis time
* ``pending``   the clock is still running and has not yet reached the target
* ``no_policy`` the ticket's priority has no SLA in the config

The response clock stops at the first agent response. A ticket resolved without
a recorded response counts as responded to at resolution, since the requester
did get an answer. If the export has no first-response times at all, the
response SLA is left unmeasured rather than approximated.

Breach rate = breached / (met + breached). Pending tickets are excluded because
their outcome is not known yet; counting them as met would flatter the numbers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from itsm_insights.calendars import (
    TWENTY_FOUR_SEVEN,
    Calendar,
    Interval,
    TwentyFourSeven,
    active_seconds,
)
from itsm_insights.config import Config

MET = "met"
BREACHED = "breached"
PENDING = "pending"
NO_POLICY = "no_policy"


def evaluate(
    tickets: pd.DataFrame,
    config: Config,
    as_of: pd.Timestamp,
    pauses: Mapping[str, list[Interval]] | None = None,
) -> pd.DataFrame:
    """Return one row per ticket with elapsed times, targets and outcomes.

    ``pauses`` maps ticket id to the intervals when its resolution clock is stopped.
    """
    as_of = _as_utc(as_of)
    pauses = pauses or {}
    calendars = config.calendars_by_priority()
    priority = tickets["priority"]
    response_target = priority.map({k: pd.Timedelta(v.response) for k, v in config.sla.items()})
    resolve_target = priority.map({k: pd.Timedelta(v.resolve) for k, v in config.sla.items()})

    response_stop = tickets["first_response"].fillna(tickets["resolved"])
    response = _outcome(tickets, response_stop, response_target, as_of, calendars, {})
    if "first_response" in tickets.attrs.get("missing_fields", ()):
        # No first-response data at all: falling back to the resolution time for every
        # ticket would report resolution speed as response speed. Leave it unmeasured.
        response = _Outcome(
            elapsed=pd.Series(pd.NaT, index=tickets.index, dtype="timedelta64[ns]"),
            status=pd.Series(pd.NA, index=tickets.index, dtype="object"),
        )
    resolution = _outcome(tickets, tickets["resolved"], resolve_target, as_of, calendars, pauses)

    return pd.DataFrame(
        {
            "id": tickets["id"],
            "priority": priority,
            "calendar": priority.map({p: c.name for p, c in calendars.items()}),
            "response_elapsed": response.elapsed,
            "response_target": response_target,
            "response_status": response.status,
            "resolve_elapsed": resolution.elapsed,
            "resolve_target": resolve_target,
            "resolve_status": resolution.status,
        }
    )


@dataclass(frozen=True)
class _Outcome:
    elapsed: pd.Series
    status: pd.Series


def _outcome(
    tickets: pd.DataFrame,
    stop: pd.Series,
    target: pd.Series,
    as_of: pd.Timestamp,
    calendars: Mapping[str, Calendar],
    pauses: Mapping[str, list[Interval]],
) -> _Outcome:
    start = tickets["created"]
    running = stop.isna()
    end = stop.where(~running, as_of)
    elapsed = _elapsed(tickets, start, end, calendars, pauses)

    status = pd.Series(MET, index=start.index, dtype="object")
    status[elapsed > target] = BREACHED
    status[running & (elapsed <= target)] = PENDING
    status[target.isna()] = NO_POLICY
    # Stop before start is bad data, not a fast response: leave it out of the rate.
    status[~running & (elapsed < pd.Timedelta(0))] = pd.NA
    elapsed = elapsed.where(elapsed >= pd.Timedelta(0))
    return _Outcome(elapsed=elapsed, status=status)


def _elapsed(
    tickets: pd.DataFrame,
    start: pd.Series,
    end: pd.Series,
    calendars: Mapping[str, Calendar],
    pauses: Mapping[str, list[Interval]],
) -> pd.Series:
    """Working time from start to end, minus paused working time.

    24x7 tickets without pauses keep the vectorised wall-clock path; the rest are
    measured one by one. Negative spans (bad data) are left negative for the caller.
    """
    wall = end - start
    cal = tickets["priority"].map(lambda p: calendars.get(p, TWENTY_FOUR_SEVEN))
    needs_calendar = ~cal.map(lambda c: isinstance(c, TwentyFourSeven)).astype(bool)
    paused = tickets["id"].astype(str).isin(set(pauses))
    slow = (needs_calendar | paused) & (wall > pd.Timedelta(0))
    if not slow.any():
        return wall
    result = wall.copy()
    ids = tickets["id"].astype(str)
    for i in tickets.index[slow]:
        seconds = active_seconds(start[i], end[i], cal[i], pauses.get(ids[i], ()))
        result[i] = pd.Timedelta(seconds=seconds)
    return result


@dataclass(frozen=True)
class BreachSummary:
    met: int
    breached: int
    pending: int

    @property
    def decided(self) -> int:
        return self.met + self.breached

    @property
    def rate(self) -> float | None:
        return self.breached / self.decided if self.decided else None

    def as_dict(self) -> dict:
        return {
            "met": self.met,
            "breached": self.breached,
            "pending": self.pending,
            "breach_rate": self.rate,
        }


def summarise(status: pd.Series) -> BreachSummary:
    counts = status.value_counts()
    return BreachSummary(
        met=int(counts.get(MET, 0)),
        breached=int(counts.get(BREACHED, 0)),
        pending=int(counts.get(PENDING, 0)),
    )


def breach_by_priority(evaluated: pd.DataFrame, config: Config) -> dict[str, dict]:
    """Response and resolution breach summaries for each configured priority."""
    out: dict[str, dict] = {}
    for priority in config.sla:
        rows = evaluated[evaluated["priority"] == priority]
        out[priority] = {
            "tickets": int(len(rows)),
            "response": summarise(rows["response_status"]),
            "resolve": summarise(rows["resolve_status"]),
        }
    return out


def _as_utc(ts: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
