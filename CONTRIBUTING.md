# Contributing

Thanks for helping. Bug reports, new loaders and clearer docs are all welcome.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Windows: .venv\Scripts\pip
pytest
ruff check . && ruff format --check .
```

## Ground rules

- **Never commit real ticket data.** Use `itsm-insights generate-demo` or hand-written fixtures.
- **Test the time logic.** Any change to how durations, calendars or SLA outcomes are computed
  needs a test with a hand-checked expected value. Boundary cases (exactly on target, one second
  over, open tickets) are where the bugs hide.
- **Keep metric definitions in sync.** If a definition changes, update `docs/METHODOLOGY.md` and
  the metrics table in the README in the same pull request.
- Small, focused pull requests are easier to review than large ones.

## Good first issues

- A loader for another tool's export format (Freshdesk, Zendesk, ServiceNow)
- `--csv` output for `analyze` so results can go straight into a spreadsheet
- Breach rate by category, not just by priority
