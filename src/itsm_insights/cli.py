"""Command-line interface: ``itsm-insights analyze`` and ``itsm-insights generate-demo``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from itsm_insights import __version__
from itsm_insights.analysis import Analysis, analyze
from itsm_insights.config import ConfigError, load_config
from itsm_insights.durations import format_duration
from itsm_insights.generator import generate, to_csv
from itsm_insights.loaders import LoaderError, load_tickets
from itsm_insights.metrics.sla import BreachSummary

app = typer.Typer(
    help="SLA, MTTR and service-desk analytics from a ticket export. Runs locally.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"itsm-insights {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    pass


@app.command("analyze")
def analyze_cmd(
    path: Annotated[Path, typer.Argument(help="Ticket export (.csv or .json).")],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="YAML config: SLA policies, columns.")
    ] = None,
    as_of: Annotated[
        str | None,
        typer.Option(
            help="Time to measure open tickets against: ISO timestamp or 'now'. "
            "Defaults to the latest timestamp in the export."
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print results as JSON.")] = False,
) -> None:
    """Calculate SLA breach rates and time to resolve, and print a summary."""
    try:
        cfg = load_config(config)
        tickets = load_tickets(path, cfg)
        result = analyze(tickets, cfg, _parse_as_of(as_of))
    except (ConfigError, LoaderError, ValueError) as exc:
        err_console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    if as_json:
        typer.echo(json.dumps(result.as_dict(), indent=2))
    else:
        _print_summary(result, path.name)


@app.command("generate-demo")
def generate_demo_cmd(
    out: Annotated[Path, typer.Option("--out", "-o", help="CSV file to write.")] = Path("demo.csv"),
    tickets: Annotated[int, typer.Option(min=1, help="Number of tickets.")] = 1000,
    days: Annotated[int, typer.Option(min=1, help="Length of the period in days.")] = 90,
    end: Annotated[
        str | None, typer.Option(help="Export time (ISO). Defaults to the current hour.")
    ] = None,
    seed: Annotated[int, typer.Option(help="Random seed, for reproducible data.")] = 42,
    timezone: Annotated[str, typer.Option(help="Timezone the service desk works in.")] = (
        "Europe/London"
    ),
    truth: Annotated[
        bool, typer.Option("--truth", help="Include the planted SLA outcome columns.")
    ] = False,
) -> None:
    """Write a synthetic ticket export. No real data involved."""
    try:
        df = generate(tickets, end=end, days=days, seed=seed, timezone=timezone, truth=truth)
    except ValueError as exc:
        err_console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    to_csv(df, out)
    open_count = int(df["resolved_at"].isna().sum())
    console.print(f"Wrote {len(df):,} synthetic tickets ({open_count:,} open) to [bold]{out}[/]")


def _parse_as_of(value: str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    if value.strip().lower() == "now":
        return pd.Timestamp.now(tz="UTC")
    try:
        return pd.Timestamp(value)
    except ValueError as exc:
        raise ValueError(f"--as-of {value!r} is not a valid timestamp") from exc


def _pct(rate: float | None) -> str:
    return "-" if rate is None else f"{rate:.1%}"


def _rate_cell(summary: BreachSummary, counts: bool = False) -> str:
    if summary.rate is None:
        return "[dim]-[/]"
    colour = "green" if summary.rate < 0.05 else "yellow" if summary.rate < 0.15 else "red"
    cell = f"[{colour}]{_pct(summary.rate)}[/]"
    if counts:
        cell += f" [dim]({summary.breached:,} of {summary.decided:,})[/]"
    return cell


def _print_summary(result: Analysis, source: str) -> None:
    console.print()
    console.rule(f"[bold]ITSM Insights[/] | {source}")
    console.print(
        f"Tickets [bold]{result.total:,}[/]  |  resolved {result.resolved:,}  |  "
        f"open {result.open:,}\n"
        f"Created {result.period_start:%Y-%m-%d} to {result.period_end:%Y-%m-%d}  |  "
        f"as of {result.as_of:%Y-%m-%d %H:%M} UTC"
    )

    console.print(
        f"\nResponse SLA breached:   [bold]{_rate_cell(result.response, counts=True)}[/]\n"
        f"Resolution SLA breached: [bold]{_rate_cell(result.resolve, counts=True)}[/]\n"
    )

    table = Table(title="SLA and time to resolve by priority", title_justify="left")
    table.add_column("Priority")
    table.add_column("Tickets", justify="right")
    for header in ("Response\nbreach", "Resolve\nbreach", "Open,\nin SLA"):
        table.add_column(header, justify="right")
    for header in ("Mean\nTTR", "Median\nTTR", "P90\nTTR"):
        table.add_column(header, justify="right", no_wrap=True)

    for priority, row in result.by_priority.items():
        stats = result.resolution_by_priority.get(priority)
        table.add_row(
            priority,
            f"{row['tickets']:,}",
            _rate_cell(row["response"]),
            _rate_cell(row["resolve"]),
            f"{row['resolve'].pending:,}",
            format_duration(stats.mean) if stats else "-",
            format_duration(stats.median) if stats else "-",
            format_duration(stats.p90) if stats else "-",
        )
    overall = result.resolution
    table.add_section()
    table.add_row(
        "[bold]All[/]",
        f"{result.total:,}",
        _rate_cell(result.response),
        _rate_cell(result.resolve),
        f"{result.resolve.pending:,}",
        format_duration(overall.mean),
        format_duration(overall.median),
        format_duration(overall.p90),
    )
    console.print(table)
    console.print(
        "[dim]Breach rate = breached / (met + breached); pending tickets are excluded. "
        "TTR = created to resolved, wall-clock (24x7).[/]"
    )

    for warning in result.warnings:
        console.print(f"[yellow]Warning: {warning}[/]")
    console.print()


if __name__ == "__main__":
    app()
