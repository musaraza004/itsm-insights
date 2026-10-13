"""Configuration: SLA policies and the column mapping for a ticket export.

A config file looks like::

    timezone: Europe/London
    columns:
      id: Issue key
      created: Created
      priority: Priority
      first_response: First Response
      resolved: Resolved
    sla:
      P1: {response: 15m, resolve: 4h, calendar: 24x7}
      P2: {response: 1h,  resolve: 8h, calendar: business}
    calendars:
      business: {days: [mon-fri], hours: "09:00-17:30", holidays: [2026-12-25]}
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from itsm_insights.calendars import TWENTY_FOUR_SEVEN, BusinessCalendar, Calendar
from itsm_insights.durations import parse_duration

#: Canonical field names used internally, in the order they appear in reports.
CANONICAL_FIELDS = (
    "id",
    "created",
    "priority",
    "status",
    "category",
    "assignee_group",
    "first_response",
    "resolved",
)
REQUIRED_FIELDS = ("id", "created", "priority")
TIMESTAMP_FIELDS = ("created", "first_response", "resolved")


class ConfigError(ValueError):
    """Raised when a config file is missing or invalid."""


class SLAPolicy(BaseModel):
    """Response and resolution targets for one priority."""

    model_config = ConfigDict(extra="forbid")

    response: timedelta
    resolve: timedelta
    # "24x7" (built in) or the name of a calendar under `calendars:`.
    calendar: str = "24x7"

    @field_validator("response", "resolve", mode="before")
    @classmethod
    def _parse(cls, value: object) -> timedelta:
        return parse_duration(value)  # type: ignore[arg-type]

    @field_validator("calendar", mode="before")
    @classmethod
    def _calendar(cls, value: object) -> str:
        text = str(value).strip()
        return "24x7" if text.lower() in {"24x7", "24/7"} else text


DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_HOURS = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$")


class CalendarConfig(BaseModel):
    """Working hours for a business calendar, e.g. ``{days: [mon-fri], hours: "09:00-17:30"}``."""

    model_config = ConfigDict(extra="forbid")

    timezone: str | None = None  # defaults to the top-level timezone
    days: list[str] = Field(default_factory=lambda: ["mon-fri"])
    hours: str = "09:00-17:00"
    holidays: list[date] = Field(default_factory=list)

    @field_validator("days")
    @classmethod
    def _days(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("a calendar needs at least one working day")
        _weekday_numbers(value)  # raises on unknown names
        return value

    @field_validator("hours")
    @classmethod
    def _hours(cls, value: str) -> str:
        opens, closes = _parse_hours(value)
        if closes <= opens:
            raise ValueError(
                f"hours {value!r}: must close after they open; overnight windows are not supported"
            )
        return value

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        return value if value is None else _check_timezone(value)

    def build(self, name: str, default_timezone: str) -> BusinessCalendar:
        opens, closes = _parse_hours(self.hours)
        return BusinessCalendar(
            name=name,
            timezone=self.timezone or default_timezone,
            workdays=frozenset(_weekday_numbers(self.days)),
            opens=opens,
            closes=closes,
            holidays=frozenset(self.holidays),
        )


def _parse_hours(value: str) -> tuple[time, time]:
    match = _HOURS.match(str(value).strip())
    if not match:
        raise ValueError(f"hours {value!r}: use HH:MM-HH:MM, e.g. 09:00-17:30")
    h1, m1, h2, m2 = (int(g) for g in match.groups())
    try:
        return time(h1, m1), time(h2, m2)
    except ValueError as exc:
        raise ValueError(f"hours {value!r}: {exc}") from exc


def _weekday_numbers(names: list[str]) -> set[int]:
    """["mon-fri", "sun"] -> {0, 1, 2, 3, 4, 6}."""
    days: set[int] = set()
    for item in names:
        parts = [p.strip().lower()[:3] for p in str(item).split("-")]
        if len(parts) > 2 or any(part not in DAY_NAMES for part in parts):
            raise ValueError(f"unknown day {item!r}; use mon, tue, ... sun or a range mon-fri")
        if len(parts) == 1:
            days.add(DAY_NAMES.index(parts[0]))
        else:
            a, b = DAY_NAMES.index(parts[0]), DAY_NAMES.index(parts[1])
            days.update(range(a, b + 1) if a <= b else [*range(a, 7), *range(0, b + 1)])
    return days


def _check_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone {value!r}; use an IANA name like 'UTC'") from exc
    return value


class HistoryColumnMap(BaseModel):
    """Column headers of a long-format history export: one row per field change."""

    model_config = ConfigDict(extra="forbid")

    id: str = "ticket_id"
    at: str = "changed_at"
    field: str = "field"
    value: str = "value"


class ColumnMap(BaseModel):
    """Maps canonical field names to the column headers in your export."""

    model_config = ConfigDict(extra="forbid")

    id: str = "ticket_id"
    created: str = "created_at"
    priority: str = "priority"
    status: str | None = "status"
    category: str | None = "category"
    assignee_group: str | None = "assignee_group"
    first_response: str | None = "first_response_at"
    resolved: str | None = "resolved_at"


def _default_sla() -> dict[str, SLAPolicy]:
    return {
        "P1": SLAPolicy(response="15m", resolve="4h"),  # type: ignore[arg-type]
        "P2": SLAPolicy(response="1h", resolve="8h"),  # type: ignore[arg-type]
        "P3": SLAPolicy(response="4h", resolve="3d"),  # type: ignore[arg-type]
        "P4": SLAPolicy(response="8h", resolve="5d"),  # type: ignore[arg-type]
    }


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str = "UTC"
    columns: ColumnMap = Field(default_factory=ColumnMap)
    sla: dict[str, SLAPolicy] = Field(default_factory=_default_sla)
    # Read now so v0.1 configs stay valid when v0.2/v0.3 start using them.
    pause_statuses: list[str] = Field(default_factory=list)
    repeat_window_days: int = Field(default=14, ge=1)
    # Raw priority value -> SLA key, e.g. {"Urgent": "P1"}. Values like "High (P3)"
    # are mapped automatically from the P-code they contain.
    priority_aliases: dict[str, str] = Field(default_factory=dict)
    # How to read numeric dates such as 05/08/2026. "auto" decides from the data.
    date_order: Literal["auto", "dmy", "mdy"] = "auto"
    # Statuses that mean the ticket is done (prefix match, case-insensitive), used to
    # flag tickets whose status and resolved time disagree.
    resolved_statuses: list[str] = Field(
        default_factory=lambda: ["Resolved", "Closed", "Done", "Solved", "Completed"]
    )
    calendars: dict[str, CalendarConfig] = Field(default_factory=dict)
    history_columns: HistoryColumnMap = Field(default_factory=HistoryColumnMap)
    # Support tiers in escalation order, e.g. [L1 Service Desk, L2 Infrastructure, Vendor].
    escalation_tiers: list[str] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return _check_timezone(value)

    @model_validator(mode="after")
    def _calendars_exist(self) -> Config:
        if "24x7" in self.calendars:
            raise ValueError("'24x7' is built in and cannot be redefined under 'calendars:'")
        for priority, policy in self.sla.items():
            if policy.calendar != "24x7" and policy.calendar not in self.calendars:
                defined = ", ".join(["24x7", *self.calendars])
                raise ValueError(
                    f"sla.{priority} uses calendar {policy.calendar!r}, which is not defined "
                    f"under 'calendars:' (defined: {defined})"
                )
        return self

    def calendar(self, name: str) -> Calendar:
        if name == "24x7":
            return TWENTY_FOUR_SEVEN
        return self.calendars[name].build(name, self.timezone)

    def calendars_by_priority(self) -> dict[str, Calendar]:
        """One calendar object per name, shared by the priorities that use it."""
        built: dict[str, Calendar] = {}
        for policy in self.sla.values():
            if policy.calendar not in built:
                built[policy.calendar] = self.calendar(policy.calendar)
        return {p: built[policy.calendar] for p, policy in self.sla.items()}

    @field_validator("sla")
    @classmethod
    def _non_empty(cls, value: dict[str, SLAPolicy]) -> dict[str, SLAPolicy]:
        if not value:
            raise ValueError("at least one priority must be defined")
        return {str(k).strip(): v for k, v in value.items()}

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def load_config(path: str | Path | None) -> Config:
    """Load a YAML config, or return the defaults when ``path`` is None."""
    if path is None:
        return Config()
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        lines = [f"invalid config in {path}:"]
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            lines.append(f"  - {loc}: {err['msg']}" if loc else f"  - {err['msg']}")
        raise ConfigError("\n".join(lines)) from exc
