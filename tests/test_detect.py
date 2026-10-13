"""Real-world export handling: column detection, date order, priorities, damage."""

import pandas as pd
import pytest

from itsm_insights.analysis import analyze
from itsm_insights.config import Config
from itsm_insights.loaders import LoaderError, check_mapping, detect, load_tickets

# A trimmed Jira Service Management export, re-saved by Excel: US dates without
# seconds, P-codes inside priority names, a time-only first-response column and
# spreadsheet error values. Mirrors the shape of real exports without real data.
JIRA_CSV = (
    "Summary,Issue key,Issue id,Issue Type,Status,Priority,Assignee,Created,Updated,Resolved,"
    "Custom field (Customer Request Type),[CHART] Date of First Response,"
    "Custom field (Time to first response)\n"
    "VPN down,AI-1,101,Incident,Resolved,High (P3),Sam,8/17/2026 15:56,8/18/2026 10:00,"
    "8/17/2026 18:00,Get IT help,03:04.6,#VALUE!\n"
    "Laptop,AI-2,102,Service Request,Resolved,Medium (P4),Ali,8/18/2026 09:00,8/20/2026 09:00,"
    "8/20/2026 09:00,Request hardware,23:58.0,-0:12\n"
    "Outage,AI-3,103,Incident,Resolved,Critical (P1),Sam,8/19/2026 10:00,8/19/2026 15:00,"
    "8/19/2026 15:00,Report a system problem,24:23.7,#VALUE!\n"
    "Printer,AI-4,104,Incident,In Progress,Low (P5),Ali,8/20/2026 11:00,8/20/2026 11:30,,"
    "Get IT help,10:00.0,#VALUE!\n"
    "Access,AI-5,105,Service Request,Resolved,Highest (P2),Sam,8/21/2026 08:00,8/21/2026 08:00,,"
    "Get IT help,11:00.0,#VALUE!\n"
)


@pytest.fixture
def jira_export(tmp_path):
    path = tmp_path / "jira.csv"
    path.write_text(JIRA_CSV, encoding="utf-8")
    return path


def write(tmp_path, text, name="t.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_jira_export_loads_with_default_config(jira_export):
    df = load_tickets(jira_export, Config(timezone="Europe/London"))
    assert list(df["id"]) == ["AI-1", "AI-2", "AI-3", "AI-4", "AI-5"]
    assert list(df["priority"]) == ["P3", "P4", "P1", "P5", "P2"]
    assert df.loc[0, "priority_raw"] == "High (P3)"
    # Month/day/year inferred from "8/17/2026"; 15:56 BST is 14:56 UTC.
    assert df.loc[0, "created"] == pd.Timestamp("2026-08-17T14:56Z")
    assert df.loc[0, "resolved"] == pd.Timestamp("2026-08-17T17:00Z")
    assert pd.isna(df.loc[3, "resolved"])
    # The Excel-damaged first-response column is ignored, not misread as today's date.
    assert df["first_response"].isna().all()
    assert "first_response" in df.attrs["missing_fields"]
    notes = " ".join(df.attrs["notes"])
    assert "Columns detected automatically" in notes and "'Issue key'" in notes
    assert "times without dates" in notes
    assert "month/day/year" in notes
    assert "High (P3) -> P3" in notes


def test_jira_export_analysis_is_honest(jira_export):
    cfg = Config(timezone="Europe/London")
    result = analyze(load_tickets(jira_export, cfg), cfg)
    assert result.resolved == 3
    # No usable first-response data: unmeasured, not approximated from resolution.
    assert result.response.rate is None
    assert result.resolve.decided == 3  # P1, P3, P4 resolved; P5 has no SLA; P2 open
    text = " ".join(result.warnings)
    assert "P5 (1)" in text and "add them under 'sla:'" in text
    assert "no first-response times" in text
    assert "resolved/closed status but no resolved time" in text  # AI-5
    by_priority = result.as_dict()["sla"]["by_priority"]
    assert by_priority["P3"]["label"] == "High"


def test_check_mapping_flags_auto_detected_columns(jira_export):
    rows = {r["field"]: r for r in check_mapping(jira_export, Config())}
    assert rows["id"]["column"] == "Issue key" and rows["id"]["auto"] is True
    assert rows["resolved"]["column"] == "Resolved"
    assert rows["category"]["column"] == "Custom field (Customer Request Type)"


def test_auto_detects_simple_names(tmp_path):
    df = load_tickets(write(tmp_path, "id,opened,prio,Priority\n1,2026-01-01,x,P1\n"), Config())
    assert df.loc[0, "id"] == "1" and df.loc[0, "priority"] == "P1"


def test_configured_column_wins_over_detection():
    resolved = detect.resolve_columns(
        {"id": "Issue id", "created": "Created"}, ["Issue key", "Issue id", "Created"]
    )
    assert resolved["id"] == {"column": "Issue id", "configured": "Issue id", "auto": False}


def test_a_header_is_never_used_twice():
    resolved = detect.resolve_columns(
        {"created": "nope", "resolved": "nope2"}, ["Created", "Closed"]
    )
    assert resolved["created"]["column"] == "Created"
    assert resolved["resolved"]["column"] == "Closed"


@pytest.mark.parametrize(
    ("samples", "expected"),
    [
        (["17/08/2026 10:00", "01/02/2026"], True),
        (["8/17/2026 10:00", "01/02/2026"], False),
        (["01/02/2026", "03/04/2026"], None),
        (["2026-08-17T10:00Z"], None),
        (["17/08/2026", "08/17/2026"], None),
    ],
)
def test_infer_dayfirst(samples, expected):
    assert detect.infer_dayfirst(samples) is expected


def test_day_first_export_parses_as_day_first(tmp_path):
    path = write(
        tmp_path, "ticket_id,created_at,priority\nA,05/08/2026 09:00,P1\nB,17/08/2026 09:00,P1\n"
    )
    df = load_tickets(path, Config())
    assert df.loc[0, "created"] == pd.Timestamp("2026-08-05T09:00Z")


def test_date_order_override(tmp_path):
    path = write(tmp_path, "ticket_id,created_at,priority\nA,05/08/2026 09:00,P1\n")
    assert load_tickets(path, Config())["created"][0].month == 5
    assert load_tickets(path, Config(date_order="dmy"))["created"][0].month == 8


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("P1", "P1"),
        ("p2", "P2"),
        ("High (P3)", "P3"),
        ("P4 - Low", "P4"),
        ("Urgent", "P1"),  # alias
        ("Whatever", "Whatever"),
    ],
)
def test_normalise_priority(raw, expected):
    keys = ["P1", "P2", "P3", "P4"]
    assert detect.normalise_priority(raw, keys, {"urgent": "P1"}) == expected


def test_priority_label():
    assert detect.priority_label("High (P3)") == "High"
    assert detect.priority_label("P4 - Low") == "Low"
    assert detect.priority_label("P1") == ""


def test_time_only_created_column_is_an_error(tmp_path):
    path = write(tmp_path, "ticket_id,created_at,priority\nA,03:04.6,P1\nB,23:58.0,P1\n")
    with pytest.raises(LoaderError, match="times without dates"):
        load_tickets(path, Config())


def test_few_bad_optional_dates_become_empty_with_a_note(tmp_path):
    path = write(
        tmp_path,
        "ticket_id,created_at,priority,resolved_at\n"
        "A,2026-01-05T09:00Z,P1,2026-01-05T10:00Z\n"
        "B,2026-01-05T09:00Z,P1,2026-01-05T11:00Z\n"
        "C,2026-01-05T09:00Z,P1,soon\n",
    )
    df = load_tickets(path, Config())
    assert df["resolved"].notna().sum() == 2
    assert any("treated as empty" in n and "'soon'" in n for n in df.attrs["notes"])


def test_reads_only_needed_columns_of_wide_exports(tmp_path):
    extra = ",".join(f"junk{i}" for i in range(300))
    row = ",".join("x" for _ in range(300))
    path = write(tmp_path, f"ticket_id,created_at,priority,{extra}\nA,2026-01-05T09:00Z,P1,{row}\n")
    df = load_tickets(path, Config())
    assert "junk0" not in df.columns and len(df) == 1
