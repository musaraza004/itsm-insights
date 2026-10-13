from datetime import timedelta
from pathlib import Path

import pytest

from itsm_insights.config import Config, ConfigError, load_config

EXAMPLE = Path(__file__).parents[1] / "examples" / "sla.yaml"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sla.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_when_no_path():
    cfg = load_config(None)
    assert cfg.sla["P1"].response == timedelta(minutes=15)
    assert cfg.columns.id == "ticket_id"


def test_example_config_loads():
    cfg = load_config(EXAMPLE)
    assert set(cfg.sla) == {"P1", "P2", "P3", "P4"}
    assert cfg.sla["P3"].resolve == timedelta(days=3)
    assert cfg.timezone == "Europe/London"


def test_spec_style_yaml(tmp_path):
    path = write(
        tmp_path,
        """
sla:
  P1: {response: 15m, resolve: 4h, calendar: 24x7}
  P2: {response: 1h,  resolve: 8h}
repeat_window_days: 14
pause_statuses: ["Waiting for customer"]
""",
    )
    cfg = load_config(path)
    assert cfg.sla["P2"].resolve == timedelta(hours=8)
    assert cfg.sla["P2"].calendar == "24x7"
    assert cfg.pause_statuses == ["Waiting for customer"]


def test_undefined_calendar_names_priority_and_choices(tmp_path):
    path = write(tmp_path, "sla:\n  P1: {response: 1h, resolve: 4h, calendar: business}\n")
    with pytest.raises(ConfigError, match=r"P1 uses calendar 'business'.*defined: 24x7"):
        load_config(path)


BUSINESS = """
timezone: Europe/London
calendars:
  business:
    days: [mon-fri]
    hours: "08:00-18:00"
    holidays: [2026-12-25, 2026-12-28]
  weekend_support:
    timezone: America/New_York
    days: [sat, sun]
    hours: "10:00-14:00"
sla:
  P1: {response: 15m, resolve: 4h, calendar: 24/7}
  P2: {response: 1h, resolve: 8h, calendar: business}
"""


def test_business_calendar_built_from_config(tmp_path):
    from datetime import date, time

    from itsm_insights.calendars import TWENTY_FOUR_SEVEN, BusinessCalendar

    cfg = load_config(write(tmp_path, BUSINESS))
    cal = cfg.calendar("business")
    assert isinstance(cal, BusinessCalendar)
    assert cal.workdays == frozenset({0, 1, 2, 3, 4})
    assert (cal.opens, cal.closes) == (time(8), time(18))
    assert cal.timezone == "Europe/London"  # inherited from the top level
    assert date(2026, 12, 28) in cal.holidays
    assert cfg.calendar("weekend_support").workdays == frozenset({5, 6})
    assert cfg.calendar("weekend_support").timezone == "America/New_York"
    by_priority = cfg.calendars_by_priority()
    assert by_priority["P1"] is TWENTY_FOUR_SEVEN
    assert by_priority["P2"].name == "business"


def test_24x7_cannot_be_redefined(tmp_path):
    path = write(tmp_path, "calendars:\n  24x7: {days: [mon]}\n")
    with pytest.raises(ConfigError, match="built in"):
        load_config(path)


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ('hours: "17:00-09:00"', "close after"),
        ('hours: "9-5"', "HH:MM-HH:MM"),
        ("days: [funday]", "unknown day"),
        ("days: []", "at least one"),
    ],
)
def test_bad_calendar_definitions(tmp_path, snippet, message):
    path = write(tmp_path, f"calendars:\n  business: {{{snippet}}}\n")
    with pytest.raises(ConfigError, match=message):
        load_config(path)


def test_bad_duration_names_the_field(tmp_path):
    path = write(tmp_path, "sla:\n  P1: {response: soon, resolve: 4h}\n")
    with pytest.raises(ConfigError, match=r"sla\.P1\.response.*invalid duration"):
        load_config(path)


def test_unknown_key_rejected(tmp_path):
    path = write(tmp_path, "sla:\n  P1: {response: 1h, resolve: 4h, respond: 1h}\n")
    with pytest.raises(ConfigError, match="respond"):
        load_config(path)


def test_unknown_timezone(tmp_path):
    path = write(tmp_path, "timezone: Mars/Olympus\n")
    with pytest.raises(ConfigError, match="unknown timezone"):
        load_config(path)


def test_empty_sla_rejected():
    with pytest.raises(ValueError, match="at least one priority"):
        Config(sla={})


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path):
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(write(tmp_path, "sla: [unclosed\n"))


def test_empty_file_gives_defaults(tmp_path):
    assert load_config(write(tmp_path, "")) == Config()
