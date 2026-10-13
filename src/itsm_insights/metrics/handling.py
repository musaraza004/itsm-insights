"""How tickets were handled: first-contact resolution, reopens, escalations.

All three need status/assignment history (see ``timeline.ticket_facts``).
Tickets without history are left out of every denominator rather than
assumed to be clean, which would flatter the rates.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Rate:
    count: int
    of: int

    @property
    def rate(self) -> float | None:
        return self.count / self.of if self.of else None

    def as_dict(self) -> dict:
        return {"count": self.count, "of": self.of, "rate": self.rate}


def _aligned(tickets: pd.DataFrame, facts: pd.DataFrame) -> pd.DataFrame:
    resolved = pd.Series(tickets["resolved"].notna().to_numpy(), index=tickets["id"].astype(str))
    joined = facts.join(resolved.rename("resolved"), how="inner")
    return joined[joined["has_history"]]


def fcr(tickets: pd.DataFrame, facts: pd.DataFrame) -> Rate:
    """Resolved tickets never reopened, escalated or reassigned / resolved tickets."""
    rows = _aligned(tickets, facts)
    resolved = rows[rows["resolved"]]
    clean = (resolved["reopens"] == 0) & (resolved["escalations"] == 0)
    clean &= resolved["reassignments"] == 0
    return Rate(int(clean.sum()), len(resolved))


def reopen_rate(tickets: pd.DataFrame, facts: pd.DataFrame) -> Rate:
    """Tickets reopened at least once / tickets resolved at least once."""
    rows = _aligned(tickets, facts)
    ever_resolved = rows["resolved"] | (rows["reopens"] > 0)
    return Rate(int((rows["reopens"] > 0).sum()), int(ever_resolved.sum()))


def escalation_rate(facts: pd.DataFrame) -> Rate:
    """Tickets moved up at least one tier / tickets with history."""
    rows = facts[facts["has_history"]]
    return Rate(int((rows["escalations"] > 0).sum()), len(rows))
