"""positions command group. DOCUMENT.md §10, §9.6."""

from __future__ import annotations

import typer

from cocoon.cli import console, get_context, guard, output_rows

app = typer.Typer(help="Position management", no_args_is_help=True)


@app.command(name="list")
@guard
def list_positions(ctx: typer.Context) -> None:
    app_ctx = get_context(ctx)
    from cocoon.persistence.repositories import PositionRepository

    repo = PositionRepository(app_ctx.database())
    rows = [
        {"ticket": p["broker_ticket_id"], "symbol": p["symbol"], "dir": p["direction"], "lots": p["volume_lots"], "entry": p["open_price"], "pnl": p["unrealized_pnl"], "origin": p["origin"]}
        for p in sorted(repo.list_open(), key=lambda p: (p["symbol"], p["broker_ticket_id"]))
    ]
    output_rows(ctx, rows, title="open positions")


@app.command()
@guard
def close(
    ctx: typer.Context,
    ticket_id: int = typer.Argument(...),
    partial: float = typer.Option(None, "--partial", help="lots to close"),
) -> None:
    app_ctx = get_context(ctx)
    if app_ctx.options.dry_run:
        console.print(f"[dim]dry-run: would close ticket {ticket_id} partial={partial}[/]")
        return
    broker = app_ctx.bridge_broker()
    broker.connect(app_ctx.config.runtime.mt5_connect_timeout_ms)
    try:
        result = broker.cancel_order(ticket_id)
        console.print(f"[green]close requested[/] ticket={ticket_id} status={result.status.value}")
        from cocoon.persistence.repositories import PositionRepository

        PositionRepository(app_ctx.database()).close(ticket_id)
    finally:
        broker.disconnect()
