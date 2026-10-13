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


def _sequences(history: pd.DataFrame, field: str) -> dict[str, list[tuple[pd.Timestamp, str]]]:
    """Per ticket, the (time, normalised value) events of one field, in time order.

    Plain-Python iteration: this runs once per history row, and per-group pandas
    operations were the bottleneck on large histories.
    """
    rows = history[history["field"] == field]
    out: dict[str, list[tuple[pd.Timestamp, str]]] = {}
    for ticket, at, value in zip(
        rows["id"].astype(str), rows["at"], rows["value"].fillna(""), strict=True
    ):
        out.setdefault(ticket, []).append((at, str(value).strip().casefold()))
    for events in out.values():
        events.sort(key=lambda e: e[0])  # stable: history order breaks ties
    return out


def _changes(values: list[str]) -> list[tuple[str, str]]:
    return [(a, b) for a, b in zip(values, values[1:], strict=False) if a != b]


def pause_intervals(
    history: pd.DataFrame, config: Config, as_of: pd.Timestamp
) -> dict[str, list[Interval]]:
    """Merged pause intervals per ticket id; tickets that never paused are omitted."""
    is_paused, _ = _matcher(config)
    out: dict[str, list[Interval]] = {}
    for ticket, events in _sequences(history, "status").items():
        intervals = [
            (at, events[i + 1][0] if i + 1 < len(events) else as_of)
            for i, (at, value) in enumerate(events)
            if is_paused(value)
        ]
        merged = merge_intervals(intervals)
        if merged:
            out[ticket] = merged
    return out


def ticket_facts(tickets: pd.DataFrame, history: pd.DataFrame, config: Config) -> pd.DataFrame:
    """One row per ticket: has_history, reopens, escalations, reassignments.

    History for ids not in ``tickets`` is ignored.
    """
    _, is_done = _matcher(config)
    tiers = {t.casefold(): i for i, t in enumerate(config.escalation_tiers)}
    ids = list(tickets["id"].astype(str))
    reopens = dict.fromkeys(ids, 0)
    escalations = dict.fromkeys(ids, 0)
    reassignments = dict.fromkeys(ids, 0)
    seen: set[str] = set()
    for field in ("status", "assignee_group", "assignee"):
        for ticket, events in _sequences(history, field).items():
            if ticket not in reopens:
                continue
            seen.add(ticket)
            changes = _changes([value for _, value in events])
            if field == "status":
                reopens[ticket] += sum(is_done(a) and not is_done(b) for a, b in changes)
                continue
            reassignments[ticket] += len(changes)
            if field == "assignee_group":
                escalations[ticket] += sum(
                    a in tiers and b in tiers and tiers[b] > tiers[a] for a, b in changes
                )
    return pd.DataFrame(
        {
            "has_history": [t in seen for t in ids],
            "reopens": [reopens[t] for t in ids],
            "escalations": [escalations[t] for t in ids],
            "reassignments": [reassignments[t] for t in ids],
        },
        index=pd.Index(ids, name="id"),
    )


def escalation_paths(history: pd.DataFrame, config: Config) -> dict[str, int]:
    """Counts of upward moves between tiers, e.g. {"L1 -> L2": 412}, busiest first."""
    tiers = {t.casefold(): i for i, t in enumerate(config.escalation_tiers)}
    names = {t.casefold(): t for t in config.escalation_tiers}
    counts: Counter[str] = Counter()
    for events in _sequences(history, "assignee_group").values():
        for a, b in _changes([value for _, value in events]):
            if a in tiers and b in tiers and tiers[b] > tiers[a]:
                counts[f"{names[a]} -> {names[b]}"] += 1
    return dict(counts.most_common())


def unknown_ticket_count(tickets: pd.DataFrame, history: pd.DataFrame) -> int:
    """Distinct ticket ids in the history that are not in the ticket export."""
    return int(
        (~pd.Index(history["id"].astype(str).unique()).isin(tickets["id"].astype(str))).sum()
    )
