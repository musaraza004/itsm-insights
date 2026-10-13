"""Turn status and assignment history into per-ticket timelines.

* Pause intervals: when a ticket sat in a status that stops the SLA clock
  (``pause_statuses``, plus ``resolved_statuses`` so the gap before a reopen
  does not count).
* Handling facts: reopens, escalations and reassignments, for FCR and friends.

A status holds from its event until the next status event for the same
ticket; the last one holds until the analysis time. The first event of each
field is its initial value, so only later differing values count as changes.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from itsm_insights.calendars import Interval, merge_intervals
from itsm_insights.config import Config


def _matcher(config: Config):
    pausing = {s.casefold() for s in config.pause_statuses}
    done = tuple(s.casefold() for s in config.resolved_statuses)

    def is_done(value: str) -> bool:
        return bool(value) and value.startswith(done)

    def is_paused(value: str) -> bool:
        return value in pausing or is_done(value)

    return is_paused, is_done


def _values(rows: pd.DataFrame) -> list[str]:
    return [str(v).strip().casefold() for v in rows["value"].fillna("")]


def pause_intervals(
    history: pd.DataFrame, config: Config, as_of: pd.Timestamp
) -> dict[str, list[Interval]]:
    """Merged pause intervals per ticket id; tickets that never paused are omitted."""
    is_paused, _ = _matcher(config)
    status = history[history["field"] == "status"]
    out: dict[str, list[Interval]] = {}
    for ticket, rows in status.groupby("id", sort=False):
        times = list(rows["at"])
        values = _values(rows)
        intervals = []
        for i, value in enumerate(values):
            if is_paused(value):
                end = times[i + 1] if i + 1 < len(times) else as_of
                intervals.append((times[i], end))
        merged = merge_intervals(intervals)
        if merged:
            out[str(ticket)] = merged
    return out


def _changes(values: list[str]) -> list[tuple[str, str]]:
    return [(a, b) for a, b in zip(values, values[1:], strict=False) if a != b]


def ticket_facts(tickets: pd.DataFrame, history: pd.DataFrame, config: Config) -> pd.DataFrame:
    """One row per ticket: has_history, reopens, escalations, reassignments.

    History for ids not in ``tickets`` is ignored.
    """
    _, is_done = _matcher(config)
    tiers = {t.casefold(): i for i, t in enumerate(config.escalation_tiers)}
    ids = tickets["id"].astype(str)
    facts = pd.DataFrame(
        {"has_history": False, "reopens": 0, "escalations": 0, "reassignments": 0},
        index=pd.Index(ids, name="id"),
    )
    known = history[history["id"].astype(str).isin(set(ids))]
    for (ticket, field), rows in known.groupby(["id", "field"], sort=False):
        ticket = str(ticket)
        facts.loc[ticket, "has_history"] = True
        values = _values(rows)
        changes = _changes(values)
        if field == "status":
            facts.loc[ticket, "reopens"] += sum(is_done(a) and not is_done(b) for a, b in changes)
        else:
            facts.loc[ticket, "reassignments"] += len(changes)
            if field == "assignee_group":
                facts.loc[ticket, "escalations"] += sum(
                    a in tiers and b in tiers and tiers[b] > tiers[a] for a, b in changes
                )
    return facts.astype(
        {"has_history": bool, "reopens": int, "escalations": int, "reassignments": int}
    )


def escalation_paths(history: pd.DataFrame, config: Config) -> dict[str, int]:
    """Counts of upward moves between tiers, e.g. {"L1 -> L2": 412}, busiest first."""
    tiers = {t.casefold(): i for i, t in enumerate(config.escalation_tiers)}
    names = {t.casefold(): t for t in config.escalation_tiers}
    counts: Counter[str] = Counter()
    groups = history[history["field"] == "assignee_group"]
    for _, rows in groups.groupby("id", sort=False):
        for a, b in _changes(_values(rows)):
            if a in tiers and b in tiers and tiers[b] > tiers[a]:
                counts[f"{names[a]} -> {names[b]}"] += 1
    return dict(counts.most_common())


def unknown_ticket_count(tickets: pd.DataFrame, history: pd.DataFrame) -> int:
    """Distinct ticket ids in the history that are not in the ticket export."""
    return int(
        (~pd.Index(history["id"].astype(str).unique()).isin(tickets["id"].astype(str))).sum()
    )
