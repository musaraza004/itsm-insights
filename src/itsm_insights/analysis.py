"""Run every metric over a ticket frame and collect the results in one object."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from itsm_insights import timeline
from itsm_insights.config import Config
from itsm_insights.loaders import detect
from itsm_insights.metrics import backlog, handling, load, mttr, sla


@dataclass
class Analysis:
    as_of: pd.Timestamp
    total: int
    resolved: int
    open: int
    period_start: pd.Timestamp
    period_end: pd.Timestamp
    response: sla.BreachSummary
    resolve: sla.BreachSummary
    by_priority: dict[str, dict]
    resolution: mttr.ResolutionStats
    resolution_by_priority: dict[str, mttr.ResolutionStats]
    priority_labels: dict[str, str] = field(default_factory=dict)
    timezone: str = "UTC"
    load: list[list[int]] = field(default_factory=list)
    backlog: dict[str, int] = field(default_factory=dict)
    calendars: dict[str, str] = field(default_factory=dict)
    # None when no history was supplied: these rates cannot be computed without it.
    handling: dict | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
            "tickets": {"total": self.total, "resolved": self.resolved, "open": self.open},
            "sla": {
                "response": self.response.as_dict(),
                "resolve": self.resolve.as_dict(),
                "calendars": self.calendars,
                "by_priority": {
                    p: {
                        "label": self.priority_labels.get(p, ""),
                        "tickets": row["tickets"],
                        "response": row["response"].as_dict(),
                        "resolve": row["resolve"].as_dict(),
                    }
                    for p, row in self.by_priority.items()
                },
            },
            "time_to_resolve": {
                "overall": self.resolution.as_dict(),
                "by_priority": {p: s.as_dict() for p, s in self.resolution_by_priority.items()},
            },
            "load": {
                "timezone": self.timezone,
                "weekdays": list(load.WEEKDAYS),
                "by_weekday_hour": self.load,
                "peak": load.peak(self.load) if self.load else None,
            },
            "backlog_ageing": self.backlog,
            "handling": self.handling,
            "warnings": self.warnings,
        }


def default_as_of(tickets: pd.DataFrame) -> pd.Timestamp:
    """Latest timestamp in the export: the best guess for when it was taken."""
    latest = pd.concat([tickets["created"], tickets["first_response"], tickets["resolved"]]).max()
    return pd.Timestamp(latest)


def analyze(
    tickets: pd.DataFrame,
    config: Config,
    as_of: pd.Timestamp | None = None,
    history: pd.DataFrame | None = None,
) -> Analysis:
    """Run every metric. ``history`` (from ``load_history``) enables clock pausing
    and the FCR, reopen and escalation rates."""
    if tickets.empty:
        raise ValueError("the export contains no tickets")
    as_of = default_as_of(tickets) if as_of is None else pd.Timestamp(as_of)
    if as_of.tzinfo is None:
        as_of = as_of.tz_localize(config.tz)
    as_of = as_of.tz_convert("UTC")

    pauses = timeline.pause_intervals(history, config, as_of) if history is not None else None
    evaluated = sla.evaluate(tickets, config, as_of, pauses=pauses)
    resolved_mask = tickets["resolved"].notna()

    return Analysis(
        as_of=as_of,
        total=len(tickets),
        resolved=int(resolved_mask.sum()),
        open=int((~resolved_mask).sum()),
        period_start=tickets["created"].min(),
        period_end=tickets["created"].max(),
        response=sla.summarise(evaluated["response_status"]),
        resolve=sla.summarise(evaluated["resolve_status"]),
        by_priority=sla.breach_by_priority(evaluated, config),
        priority_labels=_priority_labels(tickets),
        resolution=mttr.mttr(tickets),
        resolution_by_priority=mttr.mttr_by(tickets, "priority"),
        timezone=config.timezone,
        load=load.weekday_hour_counts(tickets, config.tz),
        backlog=backlog.ageing(tickets, as_of),
        calendars={p: c.name for p, c in config.calendars_by_priority().items()},
        handling=_handling(tickets, history, config) if history is not None else None,
        warnings=_data_warnings(tickets, evaluated, config, as_of, history),
    )


def _handling(tickets: pd.DataFrame, history: pd.DataFrame, config: Config) -> dict:
    facts = timeline.ticket_facts(tickets, history, config)
    return {
        "fcr": handling.fcr(tickets, facts).as_dict(),
        "reopen": handling.reopen_rate(tickets, facts).as_dict(),
        "escalation": handling.escalation_rate(facts).as_dict(),
        "escalation_paths": timeline.escalation_paths(history, config),
        "tickets_with_history": int(facts["has_history"].sum()),
    }


def _priority_labels(tickets: pd.DataFrame) -> dict[str, str]:
    """Most common original wording per priority, minus the code: P3 -> "High"."""
    if "priority_raw" not in tickets:
        return {}
    pairs = tickets[["priority", "priority_raw"]].dropna()
    return {
        str(p): detect.priority_label(group.mode().iloc[0])
        for p, group in pairs.groupby("priority")["priority_raw"]
    }


def _data_warnings(
    tickets: pd.DataFrame,
    evaluated: pd.DataFrame,
    config: Config,
    as_of: pd.Timestamp,
    history: pd.DataFrame | None = None,
) -> list[str]:
    warnings: list[str] = []

    warnings.extend(tickets.attrs.get("notes", []))

    unknown = evaluated.loc[evaluated["resolve_status"] == sla.NO_POLICY, "priority"]
    if not unknown.empty:
        counts = unknown.fillna("(blank)").value_counts()
        values = ", ".join(f"{k} ({n})" for k, n in counts.head(6).items())
        example = str(counts.index[0])
        warnings.append(
            f"{len(unknown)} ticket(s) have a priority with no SLA in the config: {values}. "
            f"They are excluded from breach rates; add them under 'sla:', e.g. "
            f"{example}: {{response: 1d, resolve: 10d}}, or map them with 'priority_aliases:'."
        )

    if "first_response" in tickets.attrs.get("missing_fields", ()):
        warnings.append(
            "The export has no first-response times, so the response SLA cannot be measured. "
            "Map a first-response timestamp column under 'columns:' to enable it."
        )

    done_prefixes = tuple(s.casefold() for s in config.resolved_statuses)
    status = tickets["status"].fillna("").str.casefold()
    looks_done = status.map(lambda v: bool(v) and v.startswith(done_prefixes))
    has_status = tickets["status"].notna().any()
    done_no_time = int((looks_done & tickets["resolved"].isna()).sum())
    time_not_done = int((~looks_done & tickets["resolved"].notna()).sum()) if has_status else 0
    if done_no_time:
        warnings.append(
            f"{done_no_time} ticket(s) have a resolved/closed status but no resolved time; "
            "they are counted as open. Check that the 'resolved' column is the resolution date."
        )
    if time_not_done:
        warnings.append(
            f"{time_not_done} ticket(s) have a resolved time but an open status "
            "(probably reopened); they are counted as resolved at that time."
        )

    backwards_response = (tickets["first_response"] < tickets["created"]).sum()
    backwards_resolve = (tickets["resolved"] < tickets["created"]).sum()
    if backwards_response:
        warnings.append(
            f"{backwards_response} ticket(s) have a first response before creation; "
            "excluded from response SLA."
        )
    if backwards_resolve:
        warnings.append(
            f"{backwards_resolve} ticket(s) are resolved before creation; "
            "excluded from resolution SLA and time to resolve."
        )

    future = (tickets["created"] > as_of).sum()
    if future:
        warnings.append(f"{future} ticket(s) were created after the analysis time {as_of}.")

    if history is None:
        if config.pause_statuses:
            warnings.append(
                "pause_statuses is set but no history file was given, so SLA clocks run "
                "without pausing. Add a status history file (CLI: --history) to enable it."
            )
        return warnings

    warnings.extend(history.attrs.get("notes", []))
    with_history = set(history["id"].astype(str))
    without = int((~tickets["id"].astype(str).isin(with_history)).sum())
    if without:
        warnings.append(
            f"{without} ticket(s) have no history; they are left out of FCR, reopen and "
            "escalation rates and their clocks are not paused."
        )
    unknown = timeline.unknown_ticket_count(tickets, history)
    if unknown:
        warnings.append(
            f"{unknown} ticket id(s) in the history are not in the ticket export and were ignored."
        )
    if history["field"].eq("assignee_group").any() and not config.escalation_tiers:
        warnings.append(
            "Assignment history is present but escalation_tiers is not set, so no move "
            "counts as an escalation. List your tiers in order, e.g. [L1, L2, Vendor]."
        )
    return warnings
