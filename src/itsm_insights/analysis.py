"""Run every metric over a ticket frame and collect the results in one object."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from itsm_insights.config import Config
from itsm_insights.metrics import backlog, load, mttr, sla


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
    timezone: str = "UTC"
    load: list[list[int]] = field(default_factory=list)
    backlog: dict[str, int] = field(default_factory=dict)
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
                "by_priority": {
                    p: {
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
            "warnings": self.warnings,
        }


def default_as_of(tickets: pd.DataFrame) -> pd.Timestamp:
    """Latest timestamp in the export: the best guess for when it was taken."""
    latest = pd.concat([tickets["created"], tickets["first_response"], tickets["resolved"]]).max()
    return pd.Timestamp(latest)


def analyze(tickets: pd.DataFrame, config: Config, as_of: pd.Timestamp | None = None) -> Analysis:
    if tickets.empty:
        raise ValueError("the export contains no tickets")
    as_of = default_as_of(tickets) if as_of is None else pd.Timestamp(as_of)
    if as_of.tzinfo is None:
        as_of = as_of.tz_localize(config.tz)
    as_of = as_of.tz_convert("UTC")

    evaluated = sla.evaluate(tickets, config, as_of)
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
        resolution=mttr.mttr(tickets),
        resolution_by_priority=mttr.mttr_by(tickets, "priority"),
        timezone=config.timezone,
        load=load.weekday_hour_counts(tickets, config.tz),
        backlog=backlog.ageing(tickets, as_of),
        warnings=_data_warnings(tickets, evaluated, config, as_of),
    )


def _data_warnings(
    tickets: pd.DataFrame, evaluated: pd.DataFrame, config: Config, as_of: pd.Timestamp
) -> list[str]:
    warnings: list[str] = []

    unknown = evaluated.loc[evaluated["resolve_status"] == sla.NO_POLICY, "priority"]
    if not unknown.empty:
        values = ", ".join(sorted({str(v) for v in unknown.fillna("(blank)").unique()})[:5])
        warnings.append(
            f"{len(unknown)} ticket(s) have a priority with no SLA in the config "
            f"({values}); they are excluded from breach rates."
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

    if config.pause_statuses:
        warnings.append(
            "pause_statuses is set but clock pausing needs status history (planned for v0.2); "
            "SLA clocks currently run continuously."
        )
    return warnings
