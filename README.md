<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/itsm-insights-logo-dark.png">
  <img src="docs/images/itsm-insights-logo-light.png" alt="ITSM Insights" width="360">
</picture>

### Service-desk SLA analytics from a ticket export, in one command or one click

[![CI](https://github.com/musaraza004/itsm-insights/actions/workflows/ci.yml/badge.svg)](https://github.com/musaraza004/itsm-insights/actions/workflows/ci.yml)
[![Web app](https://github.com/musaraza004/itsm-insights/actions/workflows/pages.yml/badge.svg)](https://musaraza004.github.io/itsm-insights/)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)
![Coverage 97%](https://img.shields.io/badge/coverage-97%25-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**[Open the web app](https://musaraza004.github.io/itsm-insights/)** ·
[Quick start](#quick-start) ·
[Metrics](#metrics) ·
[Methodology](docs/METHODOLOGY.md) ·
[Roadmap](#roadmap)

</div>

<br>

<p align="center">
  <a href="https://musaraza004.github.io/itsm-insights/?demo=1">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/images/web-app-dark.png">
      <img src="docs/images/web-app-light.png" alt="ITSM Insights web app showing SLA breach rates, time to resolve by priority, a peak-hour heatmap and backlog ageing for 5,000 demo tickets" width="860">
    </picture>
  </a>
</p>

## Overview

Most small and mid-size IT teams keep their tickets in Jira, ClickUp, Freshdesk or a
spreadsheet, but have no clear view of how they are performing. Enterprise reporting is
expensive or takes weeks to set up, so someone ends up counting tickets in Excel.

**ITSM Insights** reads the CSV or JSON export you already have and answers the questions
service managers are asked every week:

- **Are we meeting our SLAs**, and for which priorities do we fail?
- **How long do tickets really take** to resolve, and how bad is the long tail?
- **How many are fixed at first contact**, and how many get reopened or escalated?
- **When does work arrive**, so shifts can be staffed to match?
- **How old is the backlog**, and what is going stale?

It ships as a Python package with a CLI, and as a [web app](https://musaraza004.github.io/itsm-insights/)
that runs the same package in your browser.

## Highlights

| | |
| --- | --- |
| **Private by design** | Everything runs locally. The web app executes Python in the browser via WebAssembly; tickets are never uploaded. No telemetry. |
| **Works with any export** | A small YAML file maps your column names. Clear errors name the missing column, the row and the bad value. |
| **Measures SLAs the way contracts do** | Business-hours calendars with holidays and time zones, and clocks that pause while a ticket waits on the customer or a vendor. |
| **Honest metrics** | Pending tickets are not counted as met, P90 sits next to the mean, and every exclusion is reported. Definitions are in [METHODOLOGY.md](docs/METHODOLOGY.md). |
| **Verified against known answers** | A synthetic data generator plants each ticket's SLA outcome, waiting periods, reopens and escalations, and the tests require the metrics to recover every one exactly. |

## Quick start

**In the browser** (nothing to install): open
[musaraza004.github.io/itsm-insights](https://musaraza004.github.io/itsm-insights/) and drop in an
export, or click *Try with 5,000 demo tickets*.

**From the command line:**

```bash
pip install git+https://github.com/musaraza004/itsm-insights.git
itsm-insights generate-demo --tickets 5000 --out demo.csv       # also writes demo_history.csv
itsm-insights analyze demo.csv --history demo_history.csv --config examples/sla.yaml
```

Example output (abridged; the demo data depends on the date it is generated):

```text
Response SLA breached:   10.0% (498 of 4,985)
Resolution SLA breached: 8.7% (420 of 4,838)

SLA and time to resolve by priority
| Priority | Tickets |  Resp. |   Res. |  Open, |    Mean |  Median |    P90 |
|          |         | breach | breach | in SLA |     TTR |     TTR |    TTR |
|----------+---------+--------+--------+--------+---------+---------+--------|
| P1       |     148 |   9.5% |  15.1% |      2 | 12h 37m |   8h 2m |  1d 7h |
| P2       |     589 |   9.7% |  15.9% |      5 |   1d 6h | 20h 55m |  3d 0h |
| ...      |         |        |        |        |         |         |        |
SLA clocks: P1 24x7, P2-P4 business.

First-contact resolution: 70.8% (3,406 of 4,809 resolved)
Reopened:                 5.7% (274 of 4,813)
Escalated:                21.2% (1,060 of 5,000)
  L1 Service Desk -> L2 Infrastructure: 1,060
  L2 Infrastructure -> Vendor: 178
```

Without `--history` the same tickets show an 18.5% resolution breach rate, because time spent
waiting on customers and vendors counts against the target. That is the kind of difference this
tool makes visible.

Useful options:

| Option | Purpose |
| --- | --- |
| `--config sla.yaml` | Your SLA targets and column mapping (see below) |
| `--history history.csv` | Status/assignment history: pauses SLA clocks and adds FCR, reopen and escalation rates |
| `--json` | Machine-readable output, including the heatmap, backlog and handling data |
| `--as-of now` | Measure open tickets against the current time instead of the export's latest timestamp |

## Using your own export

Most exports work as they are. When a configured column is missing, ITSM Insights looks for the
names Jira, ServiceNow, Zendesk, Freshdesk and ClickUp use (`Issue key`, `Created`, `Resolved`,
`opened_at`, `Solved at`, `Custom field (Customer Request Type)` and more), skips columns that are
empty, and tells you which ones it picked. It also:

- maps priorities like `High (P3)` or `P2 - High` to `P3` and `P2` automatically
- works out whether dates are day/month or month/day from the data
- reads only the columns it needs, so 700-column Jira exports load in seconds
- ignores date columns a spreadsheet app has damaged (times without dates, `#VALUE!`) instead
  of misreading them, and says so
- flags tickets whose status and resolved time disagree

To pin things down, copy [`examples/sla.yaml`](examples/sla.yaml) and edit it:

```yaml
timezone: Europe/London            # for timestamps without a UTC offset, and the heatmap

columns:                           # only needed when detection picks the wrong column
  id: Issue key
  created: Created
  resolved: Resolved

calendars:                         # working time; 24x7 is built in
  business:
    days: [mon-fri]
    hours: "08:00-18:00"
    holidays: [2026-12-25, 2026-12-28]

sla:                               # your real targets, one per priority
  P1: {response: 15m, resolve: 4h,  calendar: 24x7}
  P2: {response: 1h,  resolve: 8h,  calendar: business}
  P3: {response: 4h,  resolve: 30h, calendar: business}   # 3 working days of 10h

pause_statuses: [Waiting for customer, Pending vendor]     # with --history
escalation_tiers: [L1 Service Desk, L2 Infrastructure, Vendor]

priority_aliases: {Urgent: P1}     # names without a P-code
date_order: auto                   # or dmy / mdy for numeric dates like 05/08/2026
```

Durations accept `s`, `m`, `h`, `d` and `w`, and can be combined (`1h30m`). On a business
calendar they are working time, so write business-day targets in hours (`1d` is 24 working hours).

SLA targets are not universal: every organisation sets its own in its service agreements. In Jira
Service Management you will find yours under *Project settings > SLAs*, including the calendar
each one uses.

**Status history** (optional) is a second file with one row per change:

```text
ticket_id,changed_at,field,value
INC1001,2026-01-05T09:00:00+00:00,status,Open
INC1001,2026-01-05T09:00:00+00:00,assignee_group,L1 Service Desk
INC1001,2026-01-05T11:20:00+00:00,status,Waiting for customer
INC1001,2026-01-06T10:05:00+00:00,status,In Progress
```

Map different column names under `history_columns:`. Fields other than status, assignee group
and assignee are ignored, so a full changelog export can be used as-is.

> **Tip:** export straight from your service desk and upload that file. Opening an export in
> Excel and saving it again can strip seconds and turn date columns into bare times.

## Metrics

| Metric | Definition |
| --- | --- |
| **Response SLA breach rate** | Share of tickets whose first response came after the target for their priority. A ticket resolved with no recorded response counts as answered at resolution. |
| **Resolution SLA breach rate** | Share of tickets resolved after the target for their priority. |
| **Time to resolve** | Created to resolved, as mean, median and P90. The median and P90 are the honest numbers; a few stale tickets inflate the mean. |
| **Peak-hour load** | Tickets created by weekday and hour in local time, shown as a 7 × 24 heatmap. |
| **Backlog ageing** | Open tickets by age: under 1 day, 1 to 3 days, 3 to 7 days, over 7 days. |
| **First-contact resolution** | Resolved tickets never reopened, escalated or reassigned, out of resolved tickets. Needs history. |
| **Reopen rate** | Tickets moved from a resolved status back to work, out of tickets resolved at least once. Needs history. |
| **Escalation rate** | Tickets moved up at least one support tier, out of all tickets. Needs history. |

How SLA outcomes are counted:

- **Breach rate = breached / (met + breached).** Open tickets still inside their target are
  *pending* and excluded, because counting them as met would flatter the result.
- An open ticket already past its target counts as **breached** at the analysis time.
- Exactly on target counts as **met**.
- Time is **working time** on the priority's calendar. With history, the resolution clock also
  stops while the ticket waits (and between a resolution and a reopen); the response clock never
  pauses.
- Tickets with no SLA for their priority, or with timestamps out of order, are excluded and
  reported as warnings, never dropped silently.

## How it is validated

Real tickets are never used. `itsm-insights generate-demo` builds a synthetic service desk:
arrivals follow office hours with a Monday-morning spike, categories mirror a typical L1 queue
(password resets, VPN, printers), and recent tickets are still open at export time.

The generator decides how much SLA time each ticket uses *before* it creates any timestamps, lays
that time out on a business-hours calendar, and inserts waiting periods, reopens and escalations,
so it knows the right answer. The test suite reads the exported files back and checks that every
planted SLA outcome, reopen, escalation and first-contact resolution is reproduced exactly, and
that measuring the same data naively (no calendars, no pausing) gets many of them wrong. Boundary
tests cover exactly-on-target, one second over, weekends, holidays and daylight-saving days.
Run `generate-demo --truth` to see the planted outcomes yourself.

## Project structure

```text
src/itsm_insights/
├── cli.py              # analyze and generate-demo commands
├── config.py           # YAML config: SLA policies, calendars, column mapping (Pydantic)
├── calendars.py        # 24x7 and business-hours working time
├── timeline.py         # pause intervals and handling facts from history
├── loaders/            # tickets (with column detection) and history
├── metrics/            # sla.py, mttr.py, handling.py, load.py, backlog.py
├── analysis.py         # runs every metric, collects warnings
└── generator.py        # synthetic tickets with planted outcomes
web/                    # the browser app (Pyodide + anime.js), deployed to GitHub Pages
docs/METHODOLOGY.md     # exact metric definitions and the reasoning behind them
tests/                  # pytest suite
```

## Roadmap

- [x] **v0.1** CSV/JSON loader, SLA breach rates (24x7), time to resolve, synthetic generator,
  CLI, browser app, peak-hour heatmap, backlog ageing
- [x] **v0.2** Business-hours calendars (working hours, weekends, holidays, time zones), SLA clock
  pausing from status history, first-contact resolution, reopen and escalation rates,
  automatic column detection ([design](docs/superpowers/specs/2026-10-13-v0.2-design.md),
  [changelog](CHANGELOG.md))
- [ ] **v0.3** Repeat incident detection, Jira and ClickUp loaders
- [ ] **v0.4** Self-contained HTML report, Docker image
- [ ] **v1.0** Documentation site, PyPI release

## Development

```bash
git clone https://github.com/musaraza004/itsm-insights.git
cd itsm-insights
python -m venv .venv
.venv/bin/pip install -e ".[dev]"     # Windows: .venv\Scripts\pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

To work on the web app locally, build the wheel next to the page and serve the folder:

```bash
mkdir -p _site && cp -r web/. _site/ && pip wheel . --no-deps -w _site
echo '{"wheel": "itsm_insights-0.2.0-py3-none-any.whl", "version": "0.2.0"}' > _site/manifest.json
python -m http.server 8765 --directory _site
```

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md); in short, never commit
real ticket data, and add a test with a hand-checked expected value for any change to the time
logic.

## License

Released under the [MIT License](LICENSE).

<br>

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/saan-technologies-logo-dark.png">
    <img src="docs/images/saan-technologies-logo-light.png" alt="SAAN Technologies" width="150">
  </picture>
  <br>
  <sub>Built by SAAN Technologies</sub>
</div>
