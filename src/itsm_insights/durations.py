"""Parse and format human-friendly durations such as ``15m``, ``4h`` or ``1h30m``."""

from __future__ import annotations

import re
from datetime import timedelta

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_PART = re.compile(r"(\d+(?:\.\d+)?)\s*([smhdw])")


def parse_duration(value: str | int | float | timedelta) -> timedelta:
    """Parse ``"15m"``, ``"4h"``, ``"3d"`` or ``"1h30m"`` into a timedelta.

    Bare numbers are read as minutes, the unit SLA targets are most often quoted in.
    """
    if isinstance(value, timedelta):
        return value
    if isinstance(value, bool):
        raise ValueError(f"invalid duration {value!r}")
    if isinstance(value, int | float):
        if value < 0:
            raise ValueError(f"duration must not be negative: {value!r}")
        return timedelta(minutes=value)

    text = str(value).strip().lower().replace(" ", "")
    if not text:
        raise ValueError("duration is empty")

    seconds = 0.0
    pos = 0
    for match in _PART.finditer(text):
        if match.start() != pos:
            break
        seconds += float(match.group(1)) * _UNITS[match.group(2)]
        pos = match.end()
    if pos != len(text) or pos == 0:
        raise ValueError(
            f"invalid duration {value!r}; use a number and unit, e.g. 15m, 4h, 3d or 1h30m"
        )
    return timedelta(seconds=seconds)


def format_duration(td: timedelta | float | None) -> str:
    """Format a duration compactly for humans: ``2d 4h``, ``3h 15m``, ``45m``, ``30s``.

    Accepts a timedelta or a number of seconds. ``None``/NaN renders as ``-``.
    """
    if td is None:
        return "-"
    seconds = td.total_seconds() if isinstance(td, timedelta) else float(td)
    if seconds != seconds:  # NaN
        return "-"
    sign = "-" if seconds < 0 else ""
    seconds = abs(round(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{sign}{days}d {hours}h"
    if hours:
        return f"{sign}{hours}h {minutes}m"
    if minutes:
        return f"{sign}{minutes}m"
    return f"{sign}{secs}s"
