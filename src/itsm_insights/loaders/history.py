"""Status and assignment history: one row per field change.

Expected shape (column names set by ``history_columns`` in the config)::

    ticket_id,changed_at,field,value
    INC1001,2026-01-05T09:00Z,status,Open
    INC1001,2026-01-05T09:00Z,assignee_group,L1 Service Desk
    INC1001,2026-01-05T11:20Z,status,Waiting for customer

The first event for a field is its initial value; later events are changes.
Fields other than status, assignee group and assignee are dropped, so a full
changelog can be passed as-is.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from itsm_insights.config import Config
from itsm_insights.loaders.generic import (
    LoaderError,
    decide_dayfirst,
    parse_timestamps,
    read_export,
    read_headers,
)

FIELDS = ("status", "assignee_group", "assignee")
COLUMNS = ["id", "at", "field", "value"]


def _field_key(value: object) -> str:
    return re.sub(r"[^a-z]+", "_", str(value).strip().lower()).strip("_")


def load_history(path: str | Path, config: Config) -> pd.DataFrame:
    """Read a history export into ``id, at (UTC), field, value``, sorted by ticket and time."""
    source = Path(path).name
    cols = config.history_columns
    wanted = {"id": cols.id, "at": cols.at, "field": cols.field, "value": cols.value}
    headers = read_headers(path)
    stripped = {h.strip(): h for h in headers}
    missing = [f"{k} (expected column {v!r})" for k, v in wanted.items() if v not in stripped]
    if missing:
        found = ", ".join(repr(h) for h in headers[:20]) or "none"
        raise LoaderError(
            f"{source} is missing history columns: {'; '.join(missing)}.\n"
            f"Columns found: {found}.\n"
            "Map them under 'history_columns:' in the config file."
        )

    raw = read_export(path, usecols=[stripped[v] for v in wanted.values()])
    out = pd.DataFrame({k: raw[stripped[v]] for k, v in wanted.items()})
    if out.empty:
        return pd.DataFrame(
            {
                "id": pd.Series(dtype="string"),
                "at": pd.Series(dtype="datetime64[ns, UTC]"),
                "field": pd.Series(dtype="string"),
                "value": pd.Series(dtype="string"),
            }
        )

    out["field"] = out["field"].map(_field_key)
    out = out[out["field"].isin(FIELDS)].copy()
    notes: list[str] = []
    dayfirst = decide_dayfirst(out["at"], config, notes)
    # Required: a change that cannot be placed in time is useless.
    out["at"] = parse_timestamps(
        out["at"], "changed_at", cols.at, config, source, dayfirst, notes, required=True
    )
    out["id"] = out["id"].astype("string").str.strip()
    out["value"] = out["value"].astype("string").str.strip()
    out["field"] = out["field"].astype("string")
    out = out.dropna(subset=["id", "at"])
    out = out.sort_values(["id", "at"], kind="stable").reset_index(drop=True)
    out.attrs["notes"] = notes
    return out[COLUMNS]
