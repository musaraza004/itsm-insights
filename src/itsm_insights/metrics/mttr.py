"""Time to resolve: mean, median and P90.

The mean is reported for familiarity, but the median and P90 are the numbers to
watch: a handful of tickets left open for weeks drags the mean far away from
what a typical requester experiences.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ResolutionStats:
    count: int
    mean: pd.Timedelta | None
    median: pd.Timedelta | None
    p90: pd.Timedelta | None

    def as_dict(self) -> dict:
        def secs(td: pd.Timedelta | None) -> float | None:
            return None if td is None else td.total_seconds()

        return {
            "count": self.count,
            "mean_seconds": secs(self.mean),
            "median_seconds": secs(self.median),
            "p90_seconds": secs(self.p90),
        }


def resolution_times(tickets: pd.DataFrame) -> pd.Series:
    """Wall-clock created → resolved per ticket; NaT for open or out-of-order tickets."""
    elapsed = tickets["resolved"] - tickets["created"]
    return elapsed.where(elapsed >= pd.Timedelta(0))


def summarise(durations: pd.Series) -> ResolutionStats:
    valid = durations.dropna()
    if valid.empty:
        return ResolutionStats(0, None, None, None)
    # Quantiles on seconds with linear interpolation (numpy's default), then back
    # to Timedelta, so results are stable across pandas versions.
    seconds = valid.dt.total_seconds()
    return ResolutionStats(
        count=int(valid.size),
        mean=pd.Timedelta(seconds=float(seconds.mean())),
        median=pd.Timedelta(seconds=float(seconds.median())),
        p90=pd.Timedelta(seconds=float(seconds.quantile(0.9))),
    )


def mttr(tickets: pd.DataFrame) -> ResolutionStats:
    return summarise(resolution_times(tickets))


def mttr_by(tickets: pd.DataFrame, column: str = "priority") -> dict[str, ResolutionStats]:
    durations = resolution_times(tickets)
    groups = tickets[column].fillna("(none)")
    return {
        str(key): summarise(durations[groups == key])
        for key in sorted(groups.unique(), key=_natural_key)
    }


def _natural_key(value: object) -> tuple:
    text = str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    return (text.rstrip("0123456789"), int(digits) if digits else 0, text)
