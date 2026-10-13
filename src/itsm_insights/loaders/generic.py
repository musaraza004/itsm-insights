"""Generic CSV/JSON loader driven by the ``columns`` mapping in the config.

Output is a DataFrame with canonical column names (see ``CANONICAL_FIELDS``),
timestamps as timezone-aware UTC, and ``priority`` mapped onto the SLA keys
where possible (the original value is kept in ``priority_raw``). Optional
columns that the export lacks are added as empty so metrics can rely on them.

Real exports are messy, so the loader is strict only where a wrong guess would
silently corrupt results (ids, creation times). Problems in optional columns
are repaired or skipped and described in ``df.attrs["notes"]``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from dateutil import parser as date_parser

from itsm_insights.config import (
    CANONICAL_FIELDS,
    REQUIRED_FIELDS,
    TIMESTAMP_FIELDS,
    Config,
)
from itsm_insights.loaders import detect


class LoaderError(ValueError):
    """Raised when an export cannot be read or does not match the column mapping."""


def read_headers(path: str | Path) -> list[str]:
    path = _existing(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return [str(c) for c in read_export(path).columns]
    if suffix not in {".csv", ".txt", ""}:
        raise LoaderError(f"unsupported file type {suffix!r}; use .csv or .json")
    try:
        return [str(c) for c in pd.read_csv(path, nrows=0, dtype=str).columns]
    except (ValueError, pd.errors.ParserError) as exc:
        raise LoaderError(f"could not parse {path.name}: {exc}") from exc


def read_export(path: str | Path, usecols: list[str] | None = None) -> pd.DataFrame:
    path = _existing(path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            df = pd.read_json(path, dtype=False)
            return df[usecols] if usecols else df
        if suffix in {".csv", ".txt", ""}:
            # Everything as text: we parse timestamps ourselves for better errors,
            # and ticket ids like "007" must not become integers. Reading only the
            # mapped columns keeps wide exports (Jira: 700+ columns) fast.
            return pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                na_values=["", *detect.EXCEL_ERRORS],
                usecols=usecols,
                low_memory=False,
            )
    except (ValueError, pd.errors.ParserError) as exc:
        raise LoaderError(f"could not parse {path.name}: {exc}") from exc
    raise LoaderError(f"unsupported file type {suffix!r}; use .csv or .json")


def check_mapping(path: str | Path, config: Config) -> list[dict]:
    """Report which column each field will use, and whether it was auto-detected."""
    resolved, _ = _resolve(path, config)
    return [
        {
            "field": field,
            "column": info["column"] or info["configured"],
            "configured": info["configured"],
            "required": field in REQUIRED_FIELDS,
            "found": info["column"] is not None,
            "auto": info["auto"],
        }
        for field, info in resolved.items()
        if info["column"] or info["configured"]
    ]


def load_tickets(path: str | Path, config: Config) -> pd.DataFrame:
    """Read an export file and normalise it using ``config.columns``."""
    resolved, raw = _resolve(path, config)
    return normalise(raw, config, source=Path(path).name, resolved=resolved)


def _resolve(path: str | Path, config: Config) -> tuple[dict[str, dict], pd.DataFrame]:
    """Read only the columns that could be used, then pick columns that have data."""
    configured = config.columns.model_dump()
    headers = read_headers(path)
    candidates = detect.candidate_headers(configured, headers)
    raw = read_export(path, usecols=candidates or None)
    filled = {str(c) for c in raw.columns if raw[c].notna().any()}
    return detect.resolve_columns(configured, headers, filled=filled), raw


def normalise(
    raw: pd.DataFrame,
    config: Config,
    source: str = "input",
    resolved: dict[str, dict] | None = None,
) -> pd.DataFrame:
    resolved = resolved or detect.resolve_columns(config.columns.model_dump(), raw.columns)
    headers = {str(c).strip(): c for c in raw.columns}
    notes: list[str] = []

    missing = [
        f"{field} (expected column {resolved[field]['configured']!r})"
        for field in REQUIRED_FIELDS
        if not resolved[field]["column"]
    ]
    if missing:
        available = ", ".join(repr(h) for h in list(headers)[:40]) or "none"
        more = "" if len(headers) <= 40 else f" and {len(headers) - 40} more"
        raise LoaderError(
            f"{source} is missing required columns: {'; '.join(missing)}.\n"
            f"Columns found: {available}{more}.\n"
            "Map your export's headers under 'columns:' in the config file."
        )

    auto = [f"{field} -> {info['column']!r}" for field, info in resolved.items() if info["auto"]]
    if auto:
        notes.append(f"Columns detected automatically: {', '.join(auto)}.")

    out = pd.DataFrame(index=raw.index)
    for field in CANONICAL_FIELDS:
        column = resolved.get(field, {}).get("column")
        out[field] = raw[headers[column.strip()]] if column else pd.NA

    samples = pd.concat([out[f].dropna().astype(str).head(2000) for f in TIMESTAMP_FIELDS])
    dayfirst = decide_dayfirst(samples, config, notes)
    for field in TIMESTAMP_FIELDS:
        out[field] = parse_timestamps(
            out[field],
            field,
            resolved[field]["column"],
            config,
            source,
            dayfirst,
            notes,
            required=field in REQUIRED_FIELDS,
        )

    out["id"] = out["id"].astype("string").str.strip()
    for field in ("status", "category", "assignee_group"):
        out[field] = out[field].astype("string").str.strip()
    raw_priority = out["priority"].astype("string").str.strip()
    out["priority_raw"] = raw_priority
    out["priority"] = raw_priority.map(
        lambda v: detect.normalise_priority(v, config.sla, config.priority_aliases),
        na_action="ignore",
    ).astype("string")
    _note_priority_mapping(raw_priority, out["priority"], notes)

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

    out = out.reset_index(drop=True)
    out.attrs["notes"] = notes
    # Timestamp fields with no usable data at all (absent, empty or ignored as damaged),
    # so metrics can tell "not in this export" apart from "not yet happened".
    out.attrs["missing_fields"] = [f for f in TIMESTAMP_FIELDS if out[f].isna().all()]
    return out


def decide_dayfirst(samples: pd.Series, config: Config, notes: list[str]) -> bool:
    """Day/month (True) or month/day (False) for numeric dates, noting the decision."""
    if config.date_order != "auto":
        return config.date_order == "dmy"
    samples = samples.dropna().astype(str)
    has_numeric = samples.str.match(r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}").any()
    decided = detect.infer_dayfirst(samples)
    if decided is None:
        if has_numeric:
            notes.append(
                "Date order could not be determined from the data (every day is 12 or "
                "less); assumed month/day/year. Set date_order: dmy in the config if wrong."
            )
        return False
    if has_numeric:
        notes.append(f"Dates read as {'day/month/year' if decided else 'month/day/year'}.")
    return decided


def _note_priority_mapping(raw: pd.Series, mapped: pd.Series, notes: list[str]) -> None:
    changed = raw.notna() & (raw != mapped)
    if not changed.any():
        return
    pairs = (
        pd.DataFrame({"raw": raw[changed], "mapped": mapped[changed]})
        .drop_duplicates()
        .sort_values("mapped")
    )
    shown = ", ".join(f"{r} -> {m}" for r, m in pairs.head(8).itertuples(index=False))
    notes.append(f"Priorities mapped to SLA keys: {shown}.")


def parse_timestamps(
    values: pd.Series,
    field: str,
    column: str | None,
    config: Config,
    source: str,
    dayfirst: bool,
    notes: list[str],
    required: bool = False,
) -> pd.Series:
    """Parse to tz-aware UTC. Naive values are taken to be in ``config.timezone``.

    Required columns must parse completely. Optional columns are repaired
    instead: unparseable values become empty, and a column that is mostly
    damaged is ignored, each with a note.
    """
    empty = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns, UTC]")
    if values.isna().all():
        return empty

    text = values.astype("string").str.strip().replace("", pd.NA)
    if detect.is_time_only(text):
        example = text.dropna().iloc[0]
        message = (
            f"column {column!r} ({field}) holds times without dates (e.g. {example!r}). "
            "This happens when a spreadsheet app reformats a date column; re-export the "
            "file from the source system without opening and saving it in Excel."
        )
        if required:
            raise LoaderError(f"{source}: {message}")
        notes.append(f"Ignored {message}")
        return empty

    try:
        parsed = pd.to_datetime(text, errors="coerce", format="mixed", dayfirst=dayfirst)
    except ValueError:
        # Mixed UTC offsets, or offsets alongside naive values: the vectorised
        # parser refuses those, so parse value by value instead.
        parsed = text.map(lambda v: _parse_one(v, dayfirst), na_action="ignore").astype(object)

    bad = text.notna() & parsed.isna()
    if bad.any():
        examples = ", ".join(f"{_row_numbers([i])} = {text[i]!r}" for i in text.index[bad][:3])
        if required:
            raise LoaderError(
                f"{source}: could not parse {bad.sum()} value(s) in column {column!r} "
                f"({field}) as dates, e.g. {examples}"
            )
        if bad.mean() > 0.5 * text.notna().mean():
            notes.append(
                f"Ignored column {column!r} ({field}): most values are not dates, e.g. {examples}."
            )
            return empty
        notes.append(
            f"{bad.sum()} value(s) in column {column!r} ({field}) are not dates and were "
            f"treated as empty, e.g. {examples}."
        )
        parsed = parsed.where(~bad)

    if isinstance(parsed.dtype, pd.DatetimeTZDtype):
        return parsed.dt.tz_convert("UTC")
    if parsed.dtype == object:
        # A mix of aware and naive values: handle element-wise.
        return pd.Series(
            [_to_utc(v, config) for v in parsed], index=values.index, dtype="datetime64[ns, UTC]"
        )
    localized = parsed.dt.tz_localize(config.tz, ambiguous="NaT", nonexistent="shift_forward")
    return localized.dt.tz_convert("UTC")


def _parse_one(value: str, dayfirst: bool) -> pd.Timestamp:
    try:
        return pd.Timestamp(date_parser.parse(value, dayfirst=dayfirst))
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def _to_utc(value: object, config: Config) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(config.tz)
    return ts.tz_convert("UTC")


def _existing(path: str | Path) -> Path:
    path = Path(path)
    if not path.is_file():
        raise LoaderError(f"input file not found: {path}")
    return path


def _row_numbers(index) -> str:
    # +2: one for the header line, one because people count rows from 1.
    rows = [str(int(i) + 2) for i in list(index)[:5]]
    more = "" if len(index) <= 5 else f" (+{len(index) - 5} more)"
    return f"row{'s' if len(rows) > 1 else ''} {', '.join(rows)}{more}"
