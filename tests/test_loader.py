import json
from pathlib import Path

import pandas as pd
import pytest

from itsm_insights.config import ColumnMap, Config
from itsm_insights.loaders import LoaderError, load_tickets


def write_csv(tmp_path: Path, text: str, name: str = "tickets.csv") -> Path:
    path = tmp_path / name
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def test_generic_csv_with_defaults(tmp_path):
    path = write_csv(
        tmp_path,
        """
ticket_id,created_at,priority,first_response_at,resolved_at
007,2026-01-05T09:00:00Z,P1,2026-01-05T09:10:00Z,2026-01-05T11:00:00Z
008,2026-01-05T10:00:00Z, P2 ,,
""",
    )
    df = load_tickets(path, Config())
    assert list(df["id"]) == ["007", "008"]  # leading zeros survive
    assert list(df["priority"]) == ["P1", "P2"]  # whitespace stripped
    assert df["created"].dt.tz is not None
    assert df.loc[0, "resolved"] == pd.Timestamp("2026-01-05T11:00:00Z")
    assert pd.isna(df.loc[1, "resolved"])
    # Optional columns absent from the export still exist, empty.
    assert df["category"].isna().all()


def test_column_mapping(tmp_path):
    path = write_csv(
        tmp_path,
        """
Issue key,Created,Priority,Resolved
OPS-1,2026-01-05 09:00,High,2026-01-05 10:00
""",
    )
    cfg = Config(
        columns=ColumnMap(
            id="Issue key",
            created="Created",
            priority="Priority",
            resolved="Resolved",
            first_response=None,
        )
    )
    df = load_tickets(path, cfg)
    assert df.loc[0, "id"] == "OPS-1"
    assert df.loc[0, "priority"] == "High"
    assert pd.isna(df.loc[0, "first_response"])


def test_naive_times_use_config_timezone(tmp_path):
    path = write_csv(
        tmp_path,
        """
ticket_id,created_at,priority
A,2026-07-01 09:00,P1
""",
    )
    df = load_tickets(path, Config(timezone="Europe/London"))
    # 09:00 BST is 08:00 UTC.
    assert df.loc[0, "created"] == pd.Timestamp("2026-07-01T08:00:00Z")


def test_mixed_offsets_and_naive_values(tmp_path):
    path = write_csv(
        tmp_path,
        """
ticket_id,created_at,priority
A,2026-07-01T09:00:00+02:00,P1
B,2026-07-01 09:00,P1
C,2026-07-01T09:00:00Z,P1
""",
    )
    df = load_tickets(path, Config(timezone="UTC"))
    assert list(df["created"]) == [
        pd.Timestamp("2026-07-01T07:00:00Z"),
        pd.Timestamp("2026-07-01T09:00:00Z"),
        pd.Timestamp("2026-07-01T09:00:00Z"),
    ]


def test_missing_required_column_lists_what_was_found(tmp_path):
    path = write_csv(tmp_path, "id,opened,prio\n1,2026-01-01,P1")
    with pytest.raises(LoaderError) as exc:
        load_tickets(path, Config())
    message = str(exc.value)
    assert "ticket_id" in message and "created_at" in message
    assert "'opened'" in message  # shows the headers it did find


def test_bad_date_reports_row_and_value(tmp_path):
    path = write_csv(
        tmp_path,
        """
ticket_id,created_at,priority
A,2026-01-05T09:00:00Z,P1
B,not a date,P1
""",
    )
    with pytest.raises(LoaderError, match=r"row 3 = 'not a date'"):
        load_tickets(path, Config())


def test_empty_created_rejected(tmp_path):
    path = write_csv(tmp_path, "ticket_id,created_at,priority\nA,,P1")
    with pytest.raises(LoaderError, match="created timestamp is empty on row 2"):
        load_tickets(path, Config())


def test_duplicate_ids_rejected(tmp_path):
    path = write_csv(
        tmp_path,
        "ticket_id,created_at,priority\nA,2026-01-01T00:00Z,P1\nA,2026-01-02T00:00Z,P1",
    )
    with pytest.raises(LoaderError, match="duplicate ticket ids"):
        load_tickets(path, Config())


def test_json_input(tmp_path):
    path = tmp_path / "tickets.json"
    path.write_text(
        json.dumps(
            [
                {"ticket_id": "A", "created_at": "2026-01-05T09:00:00Z", "priority": "P1"},
                {"ticket_id": "B", "created_at": "2026-01-05T10:00:00Z", "priority": "P2"},
            ]
        ),
        encoding="utf-8",
    )
    df = load_tickets(path, Config())
    assert list(df["id"]) == ["A", "B"]


def test_unsupported_extension(tmp_path):
    path = tmp_path / "tickets.xlsx"
    path.write_bytes(b"")
    with pytest.raises(LoaderError, match="unsupported file type"):
        load_tickets(path, Config())


def test_missing_file(tmp_path):
    with pytest.raises(LoaderError, match="not found"):
        load_tickets(tmp_path / "nope.csv", Config())
