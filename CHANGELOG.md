# Changelog

## 0.2.0 (2026-10-13)

### Added
- Business-hours calendars: working days, opening hours, holidays and timezone per calendar,
  chosen per priority. SLA targets count working time.
- SLA clock pausing from a status history file (`--history`, or the history upload in the web
  app). Waiting statuses and the gap before a reopen do not count against resolution targets.
- First-contact resolution, reopen and escalation rates, with escalation paths between tiers.
- Real-world export handling: automatic column detection for Jira, ServiceNow, Zendesk,
  Freshdesk and ClickUp names; priorities like `High (P3)` mapped to `P3`; day/month order
  inferred from the data; spreadsheet-damaged date columns ignored with a note.
- Peak-hour heatmap and backlog ageing; web app redesign.
- The demo generator writes a history file with planted pauses, reopens and escalations.

### Changed
- `generate()` returns `Demo(tickets, history)`.
- Example and demo policies express business targets in working hours (`30h`, `50h`).
- With no first-response data at all, the response SLA is reported as unmeasured instead of
  being approximated from resolution times.

## 0.1.0 (2026-10-13)

First release: generic CSV/JSON loader, 24x7 SLA breach rates, time to resolve (mean, median,
P90), synthetic generator, CLI and in-browser web app.
