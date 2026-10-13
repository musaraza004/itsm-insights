import pandas as pd
import pytest

from itsm_insights.config import Config, HistoryColumnMap
from itsm_insights.loaders import LoaderError, load_history


def write(tmp_path, text, name="history.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_long_format_history(tmp_path):
    path = write(
        tmp_path,
        "ticket_id,changed_at,field,value\n"
        "T1,2026-01-05T10:00Z,Status,Waiting for customer\n"
        "T1,2026-01-05T09:00Z,status,Open\n"
        "T1,2026-01-05T09:30Z,Assignee Group,L1\n"
        "T1,2026-01-05T09:31Z,summary,ignored\n"
        "T2,2026-01-05T08:00Z,assignee,Sam\n",
    )
    h = load_history(path, Config())
    assert list(h.columns) == ["id", "at", "field", "value"]
    # Sorted by ticket then time; unknown fields dropped; field names normalised.
    assert list(zip(h["id"], h["field"], h["value"], strict=True)) == [
        ("T1", "status", "Open"),
        ("T1", "assignee_group", "L1"),
        ("T1", "status", "Waiting for customer"),
        ("T2", "assignee", "Sam"),
    ]
    assert h.loc[0, "at"] == pd.Timestamp("2026-01-05T09:00Z")


def test_column_mapping(tmp_path):
    path = write(tmp_path, "Key,When,What,To\nAI-1,8/17/2026 15:56,Status,Resolved\n")
    cfg = Config(history_columns=HistoryColumnMap(id="Key", at="When", field="What", value="To"))
    h = load_history(path, cfg)
    assert h.loc[0, "id"] == "AI-1"
    assert h.loc[0, "at"] == pd.Timestamp("2026-08-17T15:56Z")


def test_bad_timestamp_reports_row(tmp_path):
    path = write(tmp_path, "ticket_id,changed_at,field,value\nT1,yesterday,status,Open\n")
    with pytest.raises(LoaderError, match=r"row 2 = 'yesterday'"):
        load_history(path, Config())


def test_missing_columns_listed(tmp_path):
    path = write(tmp_path, "ticket,when,field,value\nT1,2026-01-05,status,Open\n")
    with pytest.raises(LoaderError, match=r"(?s)ticket_id.*changed_at.*Columns found: 'ticket'"):
        load_history(path, Config())


def test_empty_history(tmp_path):
    h = load_history(write(tmp_path, "ticket_id,changed_at,field,value\n"), Config())
    assert h.empty and list(h.columns) == ["id", "at", "field", "value"]
