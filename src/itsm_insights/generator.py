"""Synthetic ticket generator.

Never use real company tickets for demos or tests. This generator produces
realistic-looking service-desk data: arrivals follow office hours with a Monday
morning spike, categories mirror a typical L1 queue, and a few tickets are
still open at the end of the window.

Because the generator decides each ticket's SLA outcome *before* it invents
timestamps, it knows the true answer. ``generate(..., truth=True)`` adds
``true_response_status`` and ``true_resolve_status`` columns, which the test
suite compares against what the metrics compute.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from itsm_insights.config import Config

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

GROUPS = {"L1 Service Desk": 0.70, "L2 Infrastructure": 0.25, "Vendor": 0.05}

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


def generate(
    n: int = 1000,
    *,
    end: pd.Timestamp | str | None = None,
    days: int = 90,
    seed: int = 42,
    timezone: str = "Europe/London",
    config: Config | None = None,
    truth: bool = False,
) -> pd.DataFrame:
    """Generate ``n`` tickets created during the ``days`` before ``end``.

    The export is taken at ``end``: anything that would have happened later is
    left blank, so recent tickets show up as open.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    if days < 1:
        raise ValueError("days must be at least 1")
    config = config or Config()
    rng = np.random.default_rng(seed)

    end_ts = _resolve_end(end, timezone)
    created = _arrivals(rng, n, end_ts, days, timezone)

    priorities = _choice(rng, PRIORITY_WEIGHTS, n)
    missing = sorted(set(PRIORITY_WEIGHTS) - set(config.sla))
    if missing:
        raise ValueError(f"config has no SLA for generated priorities: {', '.join(missing)}")

    resp_target = np.array([config.sla[p].response.total_seconds() for p in priorities])
    res_target = np.array([config.sla[p].resolve.total_seconds() for p in priorities])

    resp_breach = rng.random(n) < np.array([RESPONSE_BREACH[p] for p in priorities])
    res_breach = rng.random(n) < np.array([RESOLVE_BREACH[p] for p in priorities])

    # Durations land clearly inside or outside the target, never on the boundary,
    # so the planted outcome is unambiguous.
    resp_secs = np.where(
        resp_breach,
        resp_target * rng.uniform(1.05, 3.0, n),
        resp_target * rng.uniform(0.03, 0.95, n),
    )
    res_met = np.maximum(res_target * rng.uniform(0.1, 0.95, n), resp_secs + 60)
    res_met = np.minimum(res_met, res_target * 0.97)
    res_secs = np.where(res_breach, res_target * rng.uniform(1.05, 4.0, n), res_met)
    res_secs = np.maximum(res_secs, resp_secs + 60)  # resolution never precedes response

    created_s = pd.Series(created)
    first_response = created_s + pd.to_timedelta(np.round(resp_secs), unit="s")
    resolved = created_s + pd.to_timedelta(np.round(res_secs), unit="s")

    # Truncate at the export time.
    responded = first_response <= end_ts
    is_resolved = resolved <= end_ts
    first_response = first_response.where(responded)
    resolved = resolved.where(is_resolved)

    status = np.where(
        is_resolved,
        np.where(rng.random(n) < 0.8, "Resolved", "Closed"),
        np.where(
            responded,
            np.where(rng.random(n) < 0.7, "In Progress", "Waiting for customer"),
            "Open",
        ),
    )

    df = pd.DataFrame(
        {
            "ticket_id": [f"INC{100000 + i}" for i in range(n)],
            "created_at": created_s,
            "priority": priorities,
            "category": _choice(rng, CATEGORIES, n),
            "assignee_group": _choice(rng, GROUPS, n),
            "status": status,
            "first_response_at": first_response,
            "resolved_at": resolved,
        }
    )
    if truth:
        age = (end_ts - created_s).dt.total_seconds().to_numpy()
        df["true_response_status"] = _true_status(
            responded.to_numpy(), resp_breach, age, resp_target
        )
        df["true_resolve_status"] = _true_status(
            is_resolved.to_numpy(), res_breach, age, res_target
        )
    return df.sort_values("created_at", kind="stable").reset_index(drop=True)


def to_csv(df: pd.DataFrame, path) -> None:
    """Write ISO-8601 timestamps with UTC offsets, blanks for missing values."""
    out = df.copy()
    for column in ("created_at", "first_response_at", "resolved_at"):
        out[column] = out[column].map(lambda ts: "" if pd.isna(ts) else ts.isoformat())
    out.to_csv(path, index=False)


def _true_status(stopped, planted_breach, age_seconds, target_seconds) -> np.ndarray:
    return np.where(
        stopped,
        np.where(planted_breach, "breached", "met"),
        # Still running at export time: breached only once the target has passed.
        np.where(age_seconds > target_seconds, "breached", "pending"),
    )


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
