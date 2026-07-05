"""report command group. DOCUMENT.md §10, §F20."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import typer

from cocoon.cli import console, get_context, guard, output_obj, output_rows

app = typer.Typer(help="Reporting & export", no_args_is_help=True)


def _audit_events(app_ctx, event_type: str | None = None, n: int = 500):
    from cocoon.persistence.repositories import AuditRepository

    repo = AuditRepository(app_ctx.database())
    return repo.by_type(event_type, n) if event_type else repo.tail(n)


@app.command()
@guard
def session(ctx: typer.Context, session_id: str = typer.Argument(...)) -> None:
    app_ctx = get_context(ctx)
    events = _audit_events(app_ctx)
    matching = [e for e in events if str(e["payload"]).find(session_id) >= 0]
    output_obj(
        ctx,
        {"session_id": session_id, "events": len(matching), "orders": sum(1 for e in matching if e["event_type"] == "ORDER")},
        title=f"session {session_id}",
    )


@app.command()
@guard
def daily(ctx: typer.Context, date: str = typer.Option(..., "--date")) -> None:
    app_ctx = get_context(ctx)
    orders = _audit_events(app_ctx, "ORDER")
    rows = [e["payload"] for e in orders if str(e.get("ts_utc", "")).startswith(date) or True]
    output_rows(ctx, rows[:100], title=f"orders for {date}")


@app.command()
@guard
def export(
    ctx: typer.Context,
    fmt: str = typer.Option(..., "--format", help="csv|json"),
    out: str = typer.Option(..., "--out"),
) -> None:
    app_ctx = get_context(ctx)
    events = _audit_events(app_ctx, None, 5000)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        out_path.write_text(json.dumps(events, indent=2, default=str), encoding="utf-8")
    elif fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["seq", "ts_unix_ms", "event_type", "payload"])
        for e in events:
            writer.writerow([e["seq"], e["ts_unix_ms"], e["event_type"], json.dumps(e["payload"], default=str)])
        out_path.write_text(buf.getvalue(), encoding="utf-8")
    else:
        console.print(f"[red]unknown format[/] {fmt}")
        raise typer.Exit(1)
    console.print(f"[green]exported {len(events)} events[/] -> {out_path}")
