"""SLA breach calculation (v0.1: 24x7 wall-clock calendar only).

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

from dataclasses import dataclass

import pandas as pd

from itsm_insights.config import Config

MET = "met"
BREACHED = "breached"
PENDING = "pending"
NO_POLICY = "no_policy"


def evaluate(tickets: pd.DataFrame, config: Config, as_of: pd.Timestamp) -> pd.DataFrame:
    """Return one row per ticket with elapsed times, targets and outcomes."""
    as_of = _as_utc(as_of)
    priority = tickets["priority"]
    response_target = priority.map({k: pd.Timedelta(v.response) for k, v in config.sla.items()})
    resolve_target = priority.map({k: pd.Timedelta(v.resolve) for k, v in config.sla.items()})

    response_stop = tickets["first_response"].fillna(tickets["resolved"])
    response = _outcome(tickets["created"], response_stop, response_target, as_of)
    if "first_response" in tickets.attrs.get("missing_fields", ()):
        # No first-response data at all: falling back to the resolution time for every
        # ticket would report resolution speed as response speed. Leave it unmeasured.
        response = _Outcome(
            elapsed=pd.Series(pd.NaT, index=tickets.index, dtype="timedelta64[ns]"),
            status=pd.Series(pd.NA, index=tickets.index, dtype="object"),
        )
    resolution = _outcome(tickets["created"], tickets["resolved"], resolve_target, as_of)

    return pd.DataFrame(
        {
            "id": tickets["id"],
            "priority": priority,
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


def _outcome(start: pd.Series, stop: pd.Series, target: pd.Series, as_of: pd.Timestamp) -> _Outcome:
    running = stop.isna()
    end = stop.where(~running, as_of)
    elapsed = end - start

    status = pd.Series(MET, index=start.index, dtype="object")
    status[elapsed > target] = BREACHED
    status[running & (elapsed <= target)] = PENDING
    status[target.isna()] = NO_POLICY
    # Stop before start is bad data, not a fast response: leave it out of the rate.
    status[~running & (elapsed < pd.Timedelta(0))] = pd.NA
    elapsed = elapsed.where(elapsed >= pd.Timedelta(0))
    return _Outcome(elapsed=elapsed, status=status)


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
