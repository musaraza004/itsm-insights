# Methodology

How `itsm-insights` turns timestamps into metrics, and why each choice was made. The same set of
tickets can produce very different "SLA performance" depending on these choices, so they are
written down rather than buried in code.

## Input normalisation

- **Columns.** Each canonical field (`id`, `created`, `priority`, `first_response`, `resolved`,
  `status`, `category`, `assignee_group`) uses the column named under `columns:` when it exists.
  Otherwise the loader tries the names common service desks use, comparing case-, space- and
  punctuation-insensitively and unwrapping Jira's `Custom field (...)`. Empty columns are skipped,
  a column is never used for two fields, and every automatic choice is reported.
- **Priorities.** A value matching an SLA key is used as-is. Otherwise `priority_aliases` is
  checked, then the key ignoring case, then a `P<n>` code inside the text (`High (P3)` -> `P3`).
  Anything else is kept and reported as having no SLA. The original wording is kept for display.
- **Dates.** Timestamps with a UTC offset are used as given; others are interpreted in the
  configured `timezone`, then everything is converted to UTC. For numeric dates the order is
  decided from the data: a first number above 12 means day/month, a second above 12 means
  month/day. If neither appears the loader assumes month/day and says so; set `date_order` to
  override. Ambiguous local times (the repeated hour when clocks go back) become missing rather
  than guessed; non-existent times shift forward.
- **Strict where a guess would corrupt results.** Empty ids, empty or unparseable creation times,
  and duplicate ids stop the load with an error naming the rows.
- **Lenient where a column is optional.** Unparseable values in optional date columns become
  empty with a note. A column where most values are not dates, or that holds bare times (what a
  spreadsheet app leaves after reformatting a date column), is ignored with a note rather than
  misread. Spreadsheet error values (`#VALUE!`, `#N/A`, ...) count as empty.
- **Fields with no data.** If the export has no usable first-response times at all, the response
  SLA is reported as unmeasured instead of being approximated from resolution times.
- **Consistency checks.** Tickets whose status looks done (`resolved_statuses`, prefix match) but
  have no resolved time, or the reverse, are counted and reported.

## Analysis time ("as of")

Open tickets need a "now" to measure against. By default this is the latest timestamp anywhere in
the export, the best available estimate of when the export was taken, which also makes results
reproducible. Override it with `--as-of <ISO timestamp>` or `--as-of now`.

## SLA outcomes

For each ticket and each target (response, resolution) the clock runs from `created` to a stop
event:

| Target | Stop event |
| --- | --- |
| Response | `first_response`; if absent, `resolved` |
| Resolution | `resolved` |

Each ticket gets one of four outcomes:

| Outcome | Rule |
| --- | --- |
| `met` | Clock stopped and elapsed ≤ target |
| `breached` | Clock stopped and elapsed > target, **or** still running and as-of − created > target |
| `pending` | Still running and as-of − created ≤ target |
| `no_policy` | Priority has no SLA in the config |

**Breach rate = breached / (met + breached).**

Design notes:

- *Exactly on target is met.* SLA contracts are normally phrased "within N hours".
- *Running clocks that are already past target count as breaches.* They are certain to breach;
  leaving them out would hide the worst backlog.
- *Pending tickets are excluded from the denominator.* Their outcome is unknown. Counting them as
  met would lower the breach rate just because the export is recent.
- *A resolution with no recorded response satisfies the response clock.* Many tools do not record
  a separate first-response time for tickets closed in one touch.
- *Stop-before-start is bad data.* Those tickets are excluded from the affected rate and reported
  as a warning.

### Calendar (v0.1)

v0.1 measures wall-clock (24x7) time only. A ticket opened Friday 18:00 with a 4-hour target is
breached at 22:00 Friday. Business-hours calendars and clock pausing on statuses such as "Waiting
for customer" are planned for v0.2; until then a config using `calendar: business` is rejected
with a clear message rather than silently treated as 24x7.

## Time to resolve

Created → resolved for resolved tickets, wall-clock. Reported as:

- **Mean**, for comparison with other tools.
- **Median**, what a typical requester experiences.
- **P90**, the long tail: 90% of tickets were resolved within this time. Computed with linear
  interpolation between ranks (numpy's default).

Open tickets are not included; their time to resolve is not known yet. Backlog ageing
covers them.

## Peak-hour load

Tickets are counted by the weekday and hour of their `created` time, converted to the configured
`timezone` so the grid lines up with the team's working day (Monday 09:00 means 09:00 local, also
across daylight-saving changes). The busiest cell is reported; ties go to the earliest in the week.

## Backlog ageing

Open tickets (no `resolved` time) are bucketed by age at the analysis time: under 1 day, 1 to 3
days, 3 to 7 days, and over 7 days. Lower bounds are inclusive, so a ticket exactly 1 day old is in
"1 to 3 days". Tickets created after the analysis time are skipped (and already reported as a
warning).

## Validating with synthetic data

The generator plants each ticket's SLA outcome first and then derives timestamps that land clearly
inside or outside the target. Tickets whose stop event would fall after the export time are left
open. The test suite asserts that `sla.evaluate` reproduces every planted outcome exactly.
