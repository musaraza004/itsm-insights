# ITSM Insights

**Turn a ticket export into SLA, MTTR and service-desk metrics with one command, on your own machine.**

[![CI](https://github.com/musaraza004/itsm-insights/actions/workflows/ci.yml/badge.svg)](https://github.com/musaraza004/itsm-insights/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

> **Status: v0.1.** Generic CSV/JSON loader, SLA breach rates on a 24x7 clock, and time to resolve
> (mean, median, P90). Business-hours calendars and clock pausing are next; see the [roadmap](#roadmap).

## Why this exists

Small and mid-size IT teams usually have their tickets in Jira, ClickUp, Freshdesk or a
spreadsheet, but no clear view of how they are performing. Enterprise tools are expensive or
take weeks to set up, so a manager ends up counting tickets in Excel.

`itsm-insights` takes the CSV you can already export and answers, in one command:

- Are we meeting our SLAs, and for which priorities do we fail?
- How long do tickets really take to resolve, and how bad is the long tail?

## Quick start

```bash
pip install -e .
itsm-insights generate-demo --tickets 5000 --out demo.csv
itsm-insights analyze demo.csv --config examples/sla.yaml
```

Add `--json` for machine-readable output, or `--as-of now` to measure open tickets against the
current time instead of the export's latest timestamp.

## Using your own export

Map your export's column headers in a YAML config. Only `id`, `created` and `priority` are
required; anything else you leave out is treated as empty.

```yaml
timezone: Europe/London          # used for timestamps without a UTC offset

columns:
  id: Issue key
  created: Created
  priority: Priority
  first_response: First Response Date
  resolved: Resolved
  status: Status
  category: Component

sla:
  P1: {response: 15m, resolve: 4h, calendar: 24x7}
  P2: {response: 1h,  resolve: 8h, calendar: 24x7}
  P3: {response: 4h,  resolve: 3d, calendar: 24x7}
```

Durations accept `s`, `m`, `h`, `d` and `w`, and can be combined (`1h30m`). If a column is missing
or a date will not parse, the error names the column, the row number and the offending value.

## Metrics

| Metric | Definition |
| --- | --- |
| **Response SLA breach rate** | Share of tickets whose first response came after the target for their priority. A ticket resolved with no recorded response counts as responded to at resolution. |
| **Resolution SLA breach rate** | Share of tickets resolved after the target for their priority. |
| **Time to resolve (MTTR)** | Created → resolved for resolved tickets, as mean, median and P90 (linear interpolation). The median and P90 are the honest numbers; a few stale tickets inflate the mean. |

How outcomes are counted:

- **Breach rate = breached / (met + breached).** Open tickets whose clock has not yet reached the
  target are *pending* and left out, because counting them as met would flatter the result.
- An open ticket that has already passed its target counts as **breached**, measured against the
  analysis time (the latest timestamp in the export unless you pass `--as-of`).
- Exactly on target counts as **met**.
- Tickets whose priority has no SLA in the config, or whose timestamps run backwards, are excluded
  and reported as warnings rather than silently dropped.

Full definitions and the reasoning behind each choice are in
[docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Tested against known answers

Real tickets are never used. `generate-demo` builds a synthetic service desk: arrivals follow
office hours with a Monday-morning spike, categories mirror a typical L1 queue (password resets,
VPN, printers…), and recent tickets are still open at export time.

The generator decides each ticket's SLA outcome *before* it invents the timestamps, so it knows
the true answer. The test suite checks that the metrics recover exactly the breaches that were
planted. Run `generate-demo --truth` to see the planted outcome columns yourself.

## Privacy

Everything runs locally. No ticket data leaves your machine, and there is no telemetry.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"     # Windows: .venv\Scripts\pip
pytest
ruff check . && ruff format --check .
```

## Roadmap

- **v0.1** ✅ Generic CSV/JSON loader, 24x7 SLA breach, MTTR, synthetic generator, CLI summary
- **v0.2** Business-hours calendars (working hours, weekends, holidays, time zones), SLA clock
  pausing from status history, FCR, reopen and escalation rates
- **v0.3** Repeat incident detection, peak-hour heatmap, Jira and ClickUp loaders
- **v0.4** Dashboard, self-contained HTML report, Docker
- **v1.0** Documentation site, PyPI release, hosted demo

## Contributing

Issues and pull requests are welcome. Please add a test for any change to the time logic; that is
where the bugs hide.

## License

[MIT](LICENSE)
