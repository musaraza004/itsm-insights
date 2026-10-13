"""Synthetic ticket generator.

Never use real company tickets for demos or tests. This generator produces
realistic-looking service-desk data: arrivals follow office hours with a Monday
morning spike, categories mirror a typical L1 queue, tickets wait on customers
and vendors, get escalated and reopened, and a few are still open at the end
of the window.

Each ticket's timeline is built from *active* working-time segments: the
generator decides how much SLA time a ticket should use, lays it out on the
priority's calendar with ``add_working_time``, and inserts pauses between the
segments. Truth is then measured from those segments with ``working_seconds``
alone, independently of the pause and SLA code it is used to check.
``generate(..., truth=True)`` adds the truth columns.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple

import numpy as np
import pandas as pd

from itsm_insights.calendars import Calendar
from itsm_insights.config import CalendarConfig, Config, SLAPolicy

PRIORITY_WEIGHTS = {"P1": 0.03, "P2": 0.12, "P3": 0.50, "P4": 0.35}

# Chance that a ticket of each priority misses its response / resolution target.
RESPONSE_BREACH = {"P1": 0.08, "P2": 0.10, "P3": 0.12, "P4": 0.06}
RESOLVE_BREACH = {"P1": 0.15, "P2": 0.18, "P3": 0.10, "P4": 0.05}

CATEGORIES = {
    "Password reset": 22,
    "Software install": 12,
    "Access request": 14,
    "VPN": 10,
    "Email": 10,
    "Printer": 9,
    "Hardware fault": 9,
    "Network": 6,
    "New starter setup": 5,
    "Other": 3,
}

TIERS = ["L1 Service Desk", "L2 Infrastructure", "Vendor"]
AGENTS = {
    "L1 Service Desk": ["l1-ana", "l1-ben", "l1-chen", "l1-dev", "l1-eli"],
    "L2 Infrastructure": ["l2-fay", "l2-gus", "l2-hari"],
    "Vendor": ["vendor-desk"],
}
ESCALATE_TO_L2 = 0.22
ESCALATE_TO_VENDOR = 0.15  # of tickets already at L2
REASSIGN_WITHIN_L1 = 0.05
REOPEN = 0.06
PAUSES = {0: 0.65, 1: 0.27, 2: 0.08}  # number of waiting periods per ticket
WAIT_STATUSES = {"Waiting for customer": 0.7, "Pending vendor": 0.3}

# UK bank holidays 2026 (England and Wales).
UK_HOLIDAYS_2026 = [
    date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 4),
    date(2026, 5, 25), date(2026, 8, 31), date(2026, 12, 25), date(2026, 12, 28),
]  # fmt: skip

# Relative arrival rate by weekday (Mon=0) and hour of day.
WEEKDAY_WEIGHTS = np.array([1.5, 1.05, 1.0, 1.0, 0.85, 0.2, 0.12])
WORKDAY_HOURS = np.array(
    [0.2, 0.15, 0.1, 0.1, 0.1, 0.2, 0.5, 1.5, 4.5, 7.0, 6.5, 5.5,
     4.0, 5.0, 5.5, 5.0, 4.0, 2.5, 1.2, 0.8, 0.6, 0.5, 0.4, 0.3]
)  # fmt: skip
WEEKEND_HOURS = np.array(
    [0.3, 0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.8, 1.0, 1.2, 1.2,
     1.2, 1.2, 1.1, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.5, 0.4, 0.3]
)  # fmt: skip
MONDAY_MORNING_BOOST = 1.6  # extra multiplier for Monday 08:00-11:59


def demo_config() -> Config:
    """The policy the demo data is generated against; mirrors ``examples/sla.yaml``."""
    return Config(
        timezone="Europe/London",
        calendars={
            "business": CalendarConfig(
                days=["mon-fri"], hours="08:00-18:00", holidays=UK_HOLIDAYS_2026
            )
        },
        sla={
            "P1": SLAPolicy(response="15m", resolve="4h", calendar="24x7"),  # type: ignore[arg-type]
            "P2": SLAPolicy(response="1h", resolve="8h", calendar="business"),  # type: ignore[arg-type]
            "P3": SLAPolicy(response="4h", resolve="30h", calendar="business"),  # type: ignore[arg-type]
            "P4": SLAPolicy(response="8h", resolve="50h", calendar="business"),  # type: ignore[arg-type]
        },
        pause_statuses=list(WAIT_STATUSES),
        escalation_tiers=TIERS,
    )


class Demo(NamedTuple):
    tickets: pd.DataFrame
    history: pd.DataFrame


class _Event(NamedTuple):
    at: pd.Timestamp
    field: str
    value: str
    kind: str = ""  # "reopen", "escalation" or "reassign" for truth bookkeeping


def generate(
    n: int = 1000,
    *,
    end: pd.Timestamp | str | None = None,
    days: int = 90,
    seed: int = 42,
    timezone: str = "Europe/London",
    config: Config | None = None,
    truth: bool = False,
) -> Demo:
    """Generate ``n`` tickets created during the ``days`` before ``end``, with history.

    The export is taken at ``end``: anything that would have happened later is
    left out, so recent tickets show up as open (some of them mid-wait).
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    if days < 1:
        raise ValueError("days must be at least 1")
    config = config or demo_config()
    missing = sorted(set(PRIORITY_WEIGHTS) - set(config.sla))
    if missing:
        raise ValueError(f"config has no SLA for generated priorities: {', '.join(missing)}")
    calendars = config.calendars_by_priority()
    rng = np.random.default_rng(seed)

    end_ts = _resolve_end(end, timezone)
    created = _arrivals(rng, n, end_ts, days, timezone)
    priorities = _choice(rng, PRIORITY_WEIGHTS, n)
    categories = _choice(rng, CATEGORIES, n)

    tickets, history = [], []
    for i in range(n):
        ticket_id = f"INC{100000 + i}"
        row, events = _simulate(
            rng,
            created[i],
            str(priorities[i]),
            config.sla[str(priorities[i])],
            calendars[str(priorities[i])],
            end_ts,
            truth,
        )
        row.update(ticket_id=ticket_id, category=categories[i])
        tickets.append(row)
        history.extend((ticket_id, e.at, e.field, e.value) for e in events)

    columns = [
        "ticket_id", "created_at", "priority", "category", "assignee_group", "status",
        "first_response_at", "resolved_at",
    ]  # fmt: skip
    truth_columns = [c for c in tickets[0] if c.startswith("true_")]
    df = pd.DataFrame(tickets)[columns + truth_columns]
    for column in ("created_at", "first_response_at", "resolved_at"):
        df[column] = pd.to_datetime(df[column], utc=True).dt.tz_convert(timezone)
    df = df.sort_values("created_at", kind="stable").reset_index(drop=True)

    hist = pd.DataFrame(history, columns=["ticket_id", "changed_at", "field", "value"])
    hist["changed_at"] = pd.to_datetime(hist["changed_at"], utc=True).dt.tz_convert(timezone)
    hist = hist.sort_values(["ticket_id", "changed_at"], kind="stable").reset_index(drop=True)
    return Demo(df, hist)


def _seconds(x: float) -> int:
    return max(int(round(x)), 1)


def _simulate(rng, created, priority, policy, cal: Calendar, end, truth: bool):
    """Build one ticket's events, truncate them at ``end``, and derive its columns."""
    resp_target = policy.response.total_seconds()
    res_target = policy.resolve.total_seconds()
    resp_breach = rng.random() < RESPONSE_BREACH[priority]
    res_breach = rng.random() < RESOLVE_BREACH[priority]

    # Active SLA time, clearly inside or outside the target, never on the boundary.
    resp_active = _seconds(
        resp_target * (rng.uniform(1.05, 3.0) if resp_breach else rng.uniform(0.03, 0.95))
    )
    if res_breach:
        res_active = res_target * rng.uniform(1.05, 4.0)
    else:
        res_active = min(res_target * rng.uniform(0.1, 0.95), res_target * 0.97)
    res_active = _seconds(max(res_active, resp_active + 900))

    group_path = [TIERS[0]]
    if rng.random() < ESCALATE_TO_L2:
        group_path.append(TIERS[1])
        if rng.random() < ESCALATE_TO_VENDOR:
            group_path.append(TIERS[2])
    reassign = len(group_path) == 1 and rng.random() < REASSIGN_WITHIN_L1

    waits = [
        str(rng.choice(list(WAIT_STATUSES), p=list(WAIT_STATUSES.values())))
        for _ in range(int(rng.choice(list(PAUSES), p=list(PAUSES.values()))))
    ]
    if rng.random() < REOPEN:
        waits.insert(int(rng.integers(0, len(waits) + 1)), "Resolved")

    # Lay the active time out on the calendar: response first, then chunks
    # separated by pauses (waiting, or resolved-then-reopened).
    events = [_Event(created, "status", "Open"), _Event(created, "assignee_group", group_path[0])]
    first_response = cal.add_working_time(created, resp_active)
    events += [
        _Event(first_response, "status", "In Progress"),
        _Event(first_response, "assignee", str(rng.choice(AGENTS[group_path[0]]))),
    ]
    segments = [(created, first_response)]
    remaining = res_active - resp_active
    chunks = _split(rng, remaining, len(waits) + 1)
    t = first_response
    for status, chunk in zip(waits, chunks, strict=False):
        stop = cal.add_working_time(t, chunk)
        segments.append((t, stop))
        resume = stop + pd.Timedelta(seconds=_seconds(rng.uniform(0.5, 30) * 3600))
        events += [
            _Event(stop, "status", status),
            _Event(resume, "status", "In Progress", "reopen" if status == "Resolved" else ""),
        ]
        t = resume
    resolved = cal.add_working_time(t, chunks[-1])
    segments.append((t, resolved))
    events.append(_Event(resolved, "status", "Resolved"))
    if rng.random() < 0.3:
        events.append(_Event(resolved + pd.Timedelta(days=1), "status", "Closed"))

    span = resolved - first_response
    for k, group in enumerate(group_path[1:], start=1):
        at = first_response + span * (k / (len(group_path) + 1))
        at = at.floor("s")
        events += [
            _Event(at, "assignee_group", group, "escalation"),
            _Event(at, "assignee", str(rng.choice(AGENTS[group])), "reassign"),
        ]
    if reassign:
        at = (first_response + span / 3).floor("s")
        events.append(_Event(at, "assignee", "l1-cover", "reassign"))

    events.sort(key=lambda e: e.at)  # stable: same-time events keep their order
    seen = [e for e in events if e.at <= end]

    statuses = [e for e in seen if e.field == "status"]
    current = statuses[-1].value
    done = current in ("Resolved", "Closed")
    resolved_at = None
    if done:
        resolved_at = next(e.at for e in reversed(statuses) if e.value == "Resolved")
    responded_at = first_response if first_response <= end else None

    row = {
        "created_at": created,
        "priority": priority,
        "assignee_group": [e for e in seen if e.field == "assignee_group"][-1].value,
        "status": current,
        "first_response_at": responded_at,
        "resolved_at": resolved_at,
    }
    if truth:
        row.update(
            _truth(
                cal,
                created,
                segments,
                responded_at,
                resolved_at,
                end,
                resp_target,
                res_target,
                seen,
            )
        )
    return row, seen


def _truth(cal, created, segments, responded_at, resolved_at, end, resp_target, res_target, seen):
    def status(active: float, stopped: bool, target: float) -> str:
        if active > target:
            return "breached"
        return "met" if stopped else "pending"

    resp_stop = responded_at if responded_at is not None else end
    resp_active = cal.working_seconds(created, resp_stop)
    stop = resolved_at if resolved_at is not None else end
    res_active = sum(cal.working_seconds(lo, min(hi, stop)) for lo, hi in segments if lo < stop)
    reopened = any(e.kind == "reopen" for e in seen)
    escalated = any(e.kind == "escalation" for e in seen)
    reassigned = any(e.kind == "reassign" for e in seen)
    return {
        "true_response_status": status(resp_active, responded_at is not None, resp_target),
        "true_resolve_status": status(res_active, resolved_at is not None, res_target),
        "true_reopened": reopened,
        "true_escalated": escalated,
        "true_fcr": resolved_at is not None and not (reopened or escalated or reassigned),
    }


def _split(rng, total: int, parts: int) -> list[int]:
    """Split ``total`` seconds into ``parts`` positive integer chunks."""
    floor = min(60, total // parts)
    spare = total - floor * parts
    weights = rng.dirichlet(np.ones(parts))
    chunks = [floor + int(spare * w) for w in weights]
    chunks[-1] += total - sum(chunks)
    return chunks


def to_csv(df: pd.DataFrame, path) -> None:
    """Write ISO-8601 timestamps with UTC offsets, blanks for missing values."""
    out = df.copy()
    for column in out.columns:
        if isinstance(out[column].dtype, pd.DatetimeTZDtype):
            out[column] = out[column].map(lambda ts: "" if pd.isna(ts) else ts.isoformat())
    out.to_csv(path, index=False)


def history_path(tickets_path) -> str:
    """demo.csv -> demo_history.csv"""
    text = str(tickets_path)
    stem, dot, ext = text.rpartition(".")
    return f"{stem}_history.{ext}" if dot else f"{text}_history"


def _resolve_end(end, timezone: str) -> pd.Timestamp:
    if end is None:
        ts = pd.Timestamp.now(tz=timezone).floor("h")
    else:
        ts = pd.Timestamp(end)
        ts = ts.tz_localize(timezone) if ts.tzinfo is None else ts.tz_convert(timezone)
    return ts


def _arrivals(rng, n: int, end: pd.Timestamp, days: int, timezone: str) -> pd.DatetimeIndex:
    """Sample creation times from a weekday x hour intensity grid."""
    start_day = (end - timedelta(days=days)).normalize()
    hours = pd.date_range(start_day, end, freq="h", inclusive="left", tz=timezone)
    hours = hours[hours < end]
    weekday = hours.weekday.to_numpy()
    hour = hours.hour.to_numpy()
    weight = np.where(weekday < 5, WORKDAY_HOURS[hour], WEEKEND_HOURS[hour])
    weight = weight * WEEKDAY_WEIGHTS[weekday]
    weight = np.where(
        (weekday == 0) & (hour >= 8) & (hour < 12), weight * MONDAY_MORNING_BOOST, weight
    )

    picks = rng.choice(len(hours), size=n, p=weight / weight.sum())
    offsets = rng.integers(0, 3600, size=n)
    created = hours[picks] + pd.to_timedelta(offsets, unit="s")
    return created.where(created < end, end - pd.Timedelta(seconds=1))


def _choice(rng, weights: dict[str, float], n: int) -> np.ndarray:
    keys = list(weights)
    p = np.array(list(weights.values()), dtype=float)
    return rng.choice(keys, size=n, p=p / p.sum())
