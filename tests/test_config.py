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


def test_business_calendar_rejected_with_roadmap_hint(tmp_path):
    path = write(tmp_path, "sla:\n  P1: {response: 1h, resolve: 4h, calendar: business}\n")
    with pytest.raises(ConfigError, match=r"sla\.P1\.calendar.*v0\.2"):
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
