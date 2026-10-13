"""Ticket arrivals by weekday and hour of day, for shift planning."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def weekday_hour_counts(tickets: pd.DataFrame, tz: ZoneInfo | str) -> list[list[int]]:
    """7 x 24 grid of tickets created, by local weekday (Mon first) and hour."""
    local = tickets["created"].dt.tz_convert(tz)
    grid = np.zeros((7, 24), dtype=int)
    np.add.at(grid, (local.dt.weekday.to_numpy(), local.dt.hour.to_numpy()), 1)
    return grid.tolist()


def peak(grid: list[list[int]]) -> dict:
    """The busiest weekday/hour cell. Ties go to the earliest in the week."""
    arr = np.asarray(grid)
    day, hour = np.unravel_index(int(arr.argmax()), arr.shape)
    return {"weekday": WEEKDAYS[day], "hour": int(hour), "tickets": int(arr[day, hour])}
