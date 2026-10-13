"""Heuristics that let real-world exports load without hand-editing.

* Column detection: when a configured column is missing, look for the names
  that Jira, ServiceNow, Zendesk, Freshdesk and ClickUp use for the same field.
* Date order: decide day/month vs month/day from the values themselves.
* Priority normalisation: read ``High (P3)`` as ``P3``.
* Damage detection: recognise date columns Excel has reformatted into bare
  times (``03:04.6``) and spreadsheet error values (``#VALUE!``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

import pandas as pd

# Candidate headers per field, best first, compared after _key() normalisation.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "id": (
        "ticket_id", "issue key", "key", "ticket id", "ticket number", "ticket", "number",
        "task id", "request id", "case number", "incident id", "id", "issue id",
    ),
    "created": (
        "created_at", "created", "created date", "date created", "creation date", "created time",
        "opened_at", "opened", "opened at", "submitted", "date submitted",
    ),
    "priority": ("priority", "priority name", "request priority", "severity", "urgency"),
    "status": ("status", "state", "ticket status", "request status"),
    "category": (
        "category", "customer request type", "request type", "ticket type", "issue type",
        "type", "subcategory",
    ),
    "assignee_group": (
        "assignee_group", "assignment group", "group", "support team", "team", "queue",
    ),
    "first_response": (
        "first_response_at", "first response", "first response at", "first response date",
        "date of first response", "chart date of first response", "first responded at",
        "first response time", "first reply at",
    ),
    "resolved": (
        "resolved_at", "resolved", "resolved at", "resolved date", "resolution date",
        "resolved time", "date resolved", "solved at", "closed_at", "closed at", "closed",
        "closed date", "date closed",
    ),
}  # fmt: skip

EXCEL_ERRORS = ("#VALUE!", "#N/A", "#REF!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!")

_TIME_ONLY = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?(\.\d+)?$")
_NUMERIC_DATE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")
_PRIORITY_CODE = re.compile(r"\bP\s?(\d)\b", re.IGNORECASE)


def _key(header: str) -> str:
    """Compare headers loosely: Jira's ``Custom field (Request type)`` matches
    ``request type``, and case, punctuation and spacing are ignored."""
    text = str(header).strip()
    match = re.fullmatch(r"custom field \((.*)\)", text, flags=re.IGNORECASE)
    if match:
        text = match.group(1)
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def candidate_headers(configured: Mapping[str, str | None], headers: Iterable[str]) -> list[str]:
    """Every header that resolve_columns could pick: read these, then pass which are
    non-empty as ``filled`` so detection skips columns with no data."""
    wanted = {_key(c) for names in SYNONYMS.values() for c in names}
    names = {str(n).strip() for n in configured.values() if n}
    return [h for h in map(str, headers) if h.strip() in names or _key(h) in wanted]


def resolve_columns(
    configured: Mapping[str, str | None],
    headers: Iterable[str],
    filled: set[str] | None = None,
) -> dict[str, dict]:
    """Pick a column for each field.

    Returns ``{field: {"column": str | None, "configured": str | None, "auto": bool}}``.
    The configured name wins when present; otherwise the first synonym found that
    has data (when ``filled`` is given). A header is never assigned to two fields.
    """
    headers = [str(h) for h in headers]
    by_key: dict[str, str] = {}
    for header in headers:
        if filled is None or header in filled:
            by_key.setdefault(_key(header), header)
    exact = {h.strip(): h for h in headers}

    result: dict[str, dict] = {}
    taken: set[str] = set()
    # Configured names first, for every field, so auto-detection never steals them.
    for field, name in configured.items():
        column = exact.get(name.strip()) if name else None
        result[field] = {"column": column, "configured": name, "auto": False}
        if column:
            taken.add(column)
    for field, info in result.items():
        if info["column"] or field not in SYNONYMS:
            continue
        for candidate in SYNONYMS[field]:
            header = by_key.get(_key(candidate))
            if header and header not in taken:
                info.update(column=header, auto=True)
                taken.add(header)
                break
    return result


def infer_dayfirst(samples: Iterable[str]) -> bool | None:
    """True for day/month/year, False for month/day/year, None when undecidable.

    Looks only at numeric dates like ``17/08/2026``; ISO dates are unambiguous anyway.
    """
    day_first = month_first = False
    for value in samples:
        match = _NUMERIC_DATE.match(str(value).strip())
        if not match:
            continue
        a, b = int(match.group(1)), int(match.group(2))
        day_first |= a > 12
        month_first |= b > 12
        if day_first and month_first:
            return None  # contradictory: leave the parser to its default
    if day_first != month_first:
        return day_first
    return None


def is_time_only(values: pd.Series) -> bool:
    """Most non-empty values are bare times: a date column Excel has reformatted."""
    text = values.dropna().astype(str).str.strip()
    text = text[text != ""]
    if text.empty:
        return False
    return text.str.match(_TIME_ONLY).mean() > 0.5


def normalise_priority(
    value: object, sla_keys: Iterable[str], aliases: Mapping[str, str]
) -> object:
    """Map a raw priority onto an SLA key where possible.

    Order: exact key, alias (case-insensitive), key ignoring case, then a ``P<n>``
    code inside the text (``High (P3)`` -> ``P3``). Anything else is kept as-is so
    it can be reported as having no SLA.
    """
    if value is None or value is pd.NA or (isinstance(value, float) and value != value):
        return value
    text = str(value).strip()
    keys = list(sla_keys)
    if text in keys:
        return text
    folded = {k.casefold(): v for k, v in aliases.items()}
    if text.casefold() in folded:
        return folded[text.casefold()]
    for key in keys:
        if key.casefold() == text.casefold():
            return key
    match = _PRIORITY_CODE.search(text)
    if match:
        return f"P{match.group(1)}"
    return text


def priority_label(value: object) -> str:
    """Human label without the code: ``High (P3)`` -> ``High``; ``P3`` -> ``""``."""
    if value is None or value is pd.NA or (isinstance(value, float) and value != value):
        return ""
    return _PRIORITY_CODE.sub("", str(value)).replace("()", "").strip(" -:()[]")
