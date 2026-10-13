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
      P2: {response: 1h,  resolve: 8h, calendar: 24x7}
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

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
    # Business-hours calendars arrive in v0.2; v0.1 measures wall-clock time.
    calendar: Literal["24x7"] = "24x7"

    @field_validator("response", "resolve", mode="before")
    @classmethod
    def _parse(cls, value: object) -> timedelta:
        return parse_duration(value)  # type: ignore[arg-type]

    @field_validator("calendar", mode="before")
    @classmethod
    def _calendar(cls, value: object) -> object:
        if str(value).strip().lower() in {"24x7", "24/7"}:
            return "24x7"
        raise ValueError(
            f"calendar {value!r} is not supported yet; v0.1 only supports '24x7' "
            "(business-hours calendars are planned for v0.2)"
        )


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

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {value!r}; use an IANA name like 'UTC'") from exc
        return value

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
            lines.append(f"  - {loc}: {err['msg']}")
        raise ConfigError("\n".join(lines)) from exc
