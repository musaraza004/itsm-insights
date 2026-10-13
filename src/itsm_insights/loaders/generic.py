"""Generic CSV/JSON loader driven by the ``columns`` mapping in the config.

Output is a DataFrame with canonical column names (see ``CANONICAL_FIELDS``),
timestamps as timezone-aware UTC, and ``priority`` as a stripped string.
Optional columns that the export lacks are added as empty so metrics can rely
on them existing.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from itsm_insights.config import (
    CANONICAL_FIELDS,
    REQUIRED_FIELDS,
    TIMESTAMP_FIELDS,
    Config,
)


class LoaderError(ValueError):
    """Raised when an export cannot be read or does not match the column mapping."""


def read_export(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise LoaderError(f"input file not found: {path}")
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            return pd.read_json(path, dtype=False)
        if suffix in {".csv", ".txt", ""}:
            # Everything as text: we parse timestamps ourselves for better errors,
            # and ticket ids like "007" must not become integers.
            return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except (ValueError, pd.errors.ParserError) as exc:
        raise LoaderError(f"could not parse {path.name}: {exc}") from exc
    raise LoaderError(f"unsupported file type {suffix!r}; use .csv or .json")


def check_mapping(path: str | Path, config: Config) -> list[dict]:
    """Report, for each mapped field, whether its column exists in the export.

    Reads only the header row for CSV files, so it is cheap to call before loading.
    """
    path = Path(path)
    if path.suffix.lower() == ".json":
        headers = {str(c).strip() for c in read_export(path).columns}
    else:
        if not path.is_file():
            raise LoaderError(f"input file not found: {path}")
        try:
            headers = {str(c).strip() for c in pd.read_csv(path, nrows=0, dtype=str).columns}
        except (ValueError, pd.errors.ParserError) as exc:
            raise LoaderError(f"could not parse {path.name}: {exc}") from exc
    return [
        {
            "field": field,
            "column": column,
            "required": field in REQUIRED_FIELDS,
            "found": column in headers,
        }
        for field, column in config.columns.model_dump().items()
        if column
    ]


def load_tickets(path: str | Path, config: Config) -> pd.DataFrame:
    """Read an export file and normalise it using ``config.columns``."""
    return normalise(read_export(path), config, source=Path(path).name)


def normalise(raw: pd.DataFrame, config: Config, source: str = "input") -> pd.DataFrame:
    mapping = config.columns.model_dump()
    headers = {str(c).strip(): c for c in raw.columns}

    missing = [
        f"{field} (expected column {mapping[field]!r})"
        for field in REQUIRED_FIELDS
        if mapping[field] not in headers
    ]
    if missing:
        available = ", ".join(repr(h) for h in headers) or "none"
        raise LoaderError(
            f"{source} is missing required columns: {'; '.join(missing)}.\n"
            f"Columns found: {available}.\n"
            "Map your export's headers under 'columns:' in the config file."
        )

    out = pd.DataFrame(index=raw.index)
    for field in CANONICAL_FIELDS:
        column = mapping.get(field)
        if column and column in headers:
            out[field] = raw[headers[column]]
        else:
            out[field] = pd.NA

    for field in TIMESTAMP_FIELDS:
        out[field] = _parse_timestamps(out[field], field, mapping.get(field), config, source)

    out["id"] = out["id"].astype("string").str.strip()
    out["priority"] = out["priority"].astype("string").str.strip()
    for field in ("status", "category", "assignee_group"):
        out[field] = out[field].astype("string").str.strip()

    if out["id"].isna().any():
        rows = _row_numbers(out.index[out["id"].isna()])
        raise LoaderError(f"{source}: ticket id is empty on {rows}")
    if out["created"].isna().any():
        rows = _row_numbers(out.index[out["created"].isna()])
        raise LoaderError(f"{source}: created timestamp is empty on {rows}")

    dupes = out["id"][out["id"].duplicated()]
    if not dupes.empty:
        sample = ", ".join(dupes.head(5))
        raise LoaderError(f"{source}: duplicate ticket ids ({len(dupes)}), e.g. {sample}")

    return out.reset_index(drop=True)


def _parse_timestamps(
    values: pd.Series, field: str, column: str | None, config: Config, source: str
) -> pd.Series:
    """Parse to tz-aware UTC. Naive values are taken to be in ``config.timezone``."""
    if values.isna().all():
        return pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns, UTC]")

    text = values.astype("string").str.strip().replace("", pd.NA)
    try:
        parsed = pd.to_datetime(text, errors="coerce", format="mixed")
    except ValueError:
        # Mixed UTC offsets, or offsets alongside naive values: the vectorised
        # parser refuses those, so parse value by value instead.
        parsed = text.map(_parse_one, na_action="ignore").astype(object)

    bad = text.notna() & parsed.isna()
    if bad.any():
        examples = ", ".join(f"{_row_numbers([i])} = {text[i]!r}" for i in text.index[bad][:3])
        raise LoaderError(
            f"{source}: could not parse {bad.sum()} value(s) in column {column!r} "
            f"({field}) as dates, e.g. {examples}"
        )

    if isinstance(parsed.dtype, pd.DatetimeTZDtype):
        return parsed.dt.tz_convert("UTC")
    if parsed.dtype == object:
        # A mix of aware and naive values: handle element-wise.
        return pd.Series(
            [_to_utc(v, config) for v in parsed], index=values.index, dtype="datetime64[ns, UTC]"
        )
    localized = parsed.dt.tz_localize(config.tz, ambiguous="NaT", nonexistent="shift_forward")
    return localized.dt.tz_convert("UTC")


def _parse_one(value: str) -> pd.Timestamp:
    try:
        return pd.Timestamp(value)
    except (ValueError, TypeError):
        return pd.NaT


def _to_utc(value: object, config: Config) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(config.tz)
    return ts.tz_convert("UTC")


def _row_numbers(index) -> str:
    # +2: one for the header line, one because people count rows from 1.
    rows = [str(int(i) + 2) for i in list(index)[:5]]
    more = "" if len(index) <= 5 else f" (+{len(index) - 5} more)"
    return f"row{'s' if len(rows) > 1 else ''} {', '.join(rows)}{more}"
