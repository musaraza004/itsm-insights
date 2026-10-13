from __future__ import annotations

import pandas as pd
import pytest

from itsm_insights.config import Config


@pytest.fixture
def config() -> Config:
    return Config()


def utc(text: str | None) -> pd.Timestamp:
    return pd.NaT if text is None else pd.Timestamp(text, tz="UTC")


def make_tickets(rows: list[dict]) -> pd.DataFrame:
    """Build a canonical ticket frame from short dicts.

    Keys: id, priority, created, first_response, resolved (ISO strings in UTC or None).
    """
    records = []
    for i, row in enumerate(rows):
        records.append(
            {
                "id": row.get("id", f"T{i}"),
                "created": utc(row["created"]),
                "priority": row.get("priority", "P1"),
                "status": row.get("status"),
                "category": row.get("category"),
                "assignee_group": row.get("assignee_group"),
                "first_response": utc(row.get("first_response")),
                "resolved": utc(row.get("resolved")),
            }
        )
    df = pd.DataFrame.from_records(records)
    for col in ("created", "first_response", "resolved"):
        df[col] = pd.to_datetime(df[col], utc=True)
    for col in ("id", "priority", "status", "category", "assignee_group"):
        df[col] = df[col].astype("string")
    return df
