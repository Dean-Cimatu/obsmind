"""ObsMind CLI entry point."""

from typing import Annotated, Optional

import typer
from rich.console import Console

from . import __version__
from .commands.config import (
    config_app,
    context_app,
    profile_app,
    usage_command,
    doctor_command,
)
from .commands.daily import daily_app

console = Console()
INDIGO = "bright_blue"

app = typer.Typer(
    name="obsmind",
    help="ObsMind — AI companion for your Obsidian vault.",
    no_args_is_help=True,
    add_completion=False,
)

# ── subcommand groups ──────────────────────────────────────────────────────

app.add_typer(config_app,  name="config",  no_args_is_help=True)
app.add_typer(context_app, name="context", no_args_is_help=True)
app.add_typer(profile_app, name="profile", no_args_is_help=True)
app.add_typer(daily_app,   name="daily",   no_args_is_help=False)


# ── top-level commands ─────────────────────────────────────────────────────

@app.command("usage")
def usage(
    month: Annotated[Optional[str], typer.Option("--month", help="Filter to YYYY-MM")] = None,
) -> None:
    """Show API usage and cost summary."""
    usage_command(month=month)


@app.command("doctor")
def doctor(
    verbose: Annotated[bool, typer.Option("--verbose", help="Show stack traces")] = False,
) -> None:
    """Run diagnostics — verify the full ObsMind setup."""
    doctor_command(verbose=verbose)


# ── version callback ───────────────────────────────────────────────────────

def version_callback(value: bool) -> None:
    if value:
        console.print(f"[{INDIGO}]ObsMind[/{INDIGO}] v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-v", callback=version_callback, is_eager=True, help="Print version"),
    ] = None,
) -> None:
    """ObsMind — AI companion for your Obsidian vault."""
