"""Backlog ageing: how long open tickets have been waiting."""

from __future__ import annotations

import math

import pandas as pd

#: Bucket label and its upper bound in days (exclusive).
BUCKETS = (("0-1d", 1.0), ("1-3d", 3.0), ("3-7d", 7.0), ("7d+", math.inf))


def ageing(tickets: pd.DataFrame, as_of: pd.Timestamp) -> dict[str, int]:
    """Count open tickets by age at ``as_of``. Tickets created after ``as_of`` are skipped."""
    open_ = tickets[tickets["resolved"].isna()]
    days = (as_of - open_["created"]).dt.total_seconds() / 86400
    days = days[days >= 0]
    counts: dict[str, int] = {}
    lower = 0.0
    for label, upper in BUCKETS:
        counts[label] = int(((days >= lower) & (days < upper)).sum())
        lower = upper
    return counts
