"""Commands: config, context, usage, doctor, profile."""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..core import ai as ai_core
from ..core.context import update_context, load_context, CONTEXT_FILE
from ..core.index import load_index, IndexError
from ..core.obsflow import check_available, is_available, ObsFlowNotFoundError, version as obs_version
from ..core.profiles import PROFILES, get_profile
from ..core.usage import read_usage, summarise_usage
from ..core.vault import load_config, save_config, resolve_vault_path, OBSMIND_RC

console = Console()

INDIGO = "bright_blue"
AMBER  = "yellow"
DIM    = "dim"

# ── config ─────────────────────────────────────────────────────────────────

config_app = typer.Typer(help="View and update ObsMind configuration.")


@config_app.command("show")
def config_show() -> None:
    """Print all config values (API key redacted)."""
    cfg = load_config()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    api_display = (
        f"[green]set[/green] ({api_key[:8]}…)" if api_key else "[red]not set[/red]"
    )

    try:
        vault_path = resolve_vault_path(cfg)
        vault_display = f"[green]{vault_path}[/green]"
    except FileNotFoundError:
        vault_display = f"[red]{cfg.get('vault_path') or '(not set)'}[/red]"

    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column("key",   style="bold", min_width=22)
    table.add_column("value")

    table.add_row("ANTHROPIC_API_KEY", api_display)
    table.add_row("vault_path",        vault_display)
    table.add_row("profile",           cfg.get("profile", "dev"))
    table.add_row("daily_notes_folder",cfg.get("daily_notes_folder", "Daily Notes"))
    table.add_row("priorities_note",   cfg.get("priorities_note") or "[dim](not set)[/dim]")
    table.add_row("context_notes",     ", ".join(cfg.get("context_notes", [])) or "[dim](none)[/dim]")
    table.add_row("config_file",       str(Path.home() / ".obsmind" / "config.json"))

    console.print(f"\n[{INDIGO}]ObsMind[/{INDIGO}] config\n")
    console.print(table)
    console.print()


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Config key to update"),
    value: str = typer.Argument(help="New value"),
) -> None:
    """Set a config value."""
    ALLOWED = {"vault_path", "profile", "daily_notes_folder", "priorities_note"}
    if key not in ALLOWED:
        console.print(f"[red]✗ Unknown key: {key}[/red]")
        console.print(f"[dim]  Valid keys: {', '.join(sorted(ALLOWED))}[/dim]")
        raise typer.Exit(1)

    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
    console.print(f"[green]✓[/green] {key} = {value}")


# ── context ────────────────────────────────────────────────────────────────

context_app = typer.Typer(help="Manage the vault context cache.")


@context_app.command("update")
def context_update() -> None:
    """Rebuild the context cache from vault contents."""
    cfg = load_config()
    try:
        resolve_vault_path(cfg)
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    with console.status("[dim]Reading vault…[/dim]"):
        try:
            path = update_context(cfg)
        except Exception as e:
            console.print(f"[red]✗ Failed to build context: {e}[/red]")
            raise typer.Exit(1)

    size = path.stat().st_size
    console.print(f"[green]✓[/green] Context updated → [dim]{path}[/dim] ({size:,} bytes)")


@context_app.command("show")
def context_show() -> None:
    """Print the cached system-prompt context."""
    ctx = load_context()
    if ctx is None:
        console.print("[yellow]⚠  No context cache found.[/yellow]")
        console.print("[dim]  Fix: run 'obsmind context update' first.[/dim]")
        raise typer.Exit(1)
    console.print(Panel(ctx, title="ObsMind Context", border_style=AMBER))


# ── usage ──────────────────────────────────────────────────────────────────

def usage_command(
    month: Annotated[Optional[str], typer.Option("--month", help="Filter to YYYY-MM")] = None,
) -> None:
    """Show API usage and cost summary."""
    if month is None:
        month = datetime.now().strftime("%Y-%m")

    records = read_usage(month=month)
    summary = summarise_usage(records)

    console.print(f"\n[{INDIGO}]ObsMind[/{INDIGO}] usage  [dim]{month}[/dim]\n")

    if not records:
        console.print("[dim]  No API calls recorded for this period.[/dim]\n")
        return

    table = Table(box=None, show_header=True, padding=(0, 2))
    table.add_column("Model",          style="bold")
    table.add_column("Calls",          justify="right")
    table.add_column("Input tok",      justify="right")
    table.add_column("Output tok",     justify="right")
    table.add_column("Cost (USD)",     justify="right")

    for model, s in summary["by_model"].items():
        table.add_row(
            model,
            str(s["calls"]),
            f"{s['input_tokens']:,}",
            f"{s['output_tokens']:,}",
            f"${s['cost_usd']:.5f}",
        )

    console.print(table)
    console.print(
        f"\n  [bold]Total[/bold]  "
        f"{summary['total_calls']} calls  "
        f"${summary['total_cost_usd']:.5f}\n"
    )


# ── doctor ─────────────────────────────────────────────────────────────────

def doctor_command(verbose: bool = False) -> None:
    """Run diagnostics and verify the full ObsMind setup."""
    console.print(f"\n[{INDIGO}]ObsMind[/{INDIGO}] doctor\n")

    all_ok = True

    def check(label: str, ok: bool, fix: str = "") -> None:
        nonlocal all_ok
        if ok:
            console.print(f"  [green]✓[/green]  {label}")
        else:
            console.print(f"  [red]✗[/red]  {label}")
            if fix:
                console.print(f"      [dim]{fix}[/dim]")
            all_ok = False

    # 1. Python version
    major, minor = sys.version_info.major, sys.version_info.minor
    check(
        f"Python {major}.{minor} (≥ 3.11 required)",
        (major, minor) >= (3, 11),
        "Fix: install Python 3.11+ via pyenv or Homebrew.",
    )

    # 2. ANTHROPIC_API_KEY
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    check(
        "ANTHROPIC_API_KEY set",
        bool(api_key),
        "Fix: export ANTHROPIC_API_KEY=sk-ant-...",
    )

    # 3. Vault path
    cfg = load_config()
    vault_ok = False
    try:
        vp = resolve_vault_path(cfg)
        vault_ok = True
        check(f"Vault path resolves ({vp})", True)
    except FileNotFoundError as e:
        check("Vault path resolves", False, str(e).split("\n")[1] if "\n" in str(e) else str(e))

    # 4. obs CLI reachable
    obs_ok = False
    try:
        obs_bin = check_available()
        ver = obs_version()
        obs_ok = True
        check(f"obs CLI reachable ({ver})", True)
    except ObsFlowNotFoundError as e:
        check("obs CLI reachable", False, str(e).split("\n")[1] if "\n" in str(e) else str(e))

    # 5. ObsFlow index (only if vault found)
    if vault_ok:
        try:
            vp = resolve_vault_path(cfg)
            load_index(vp)
            check("ObsFlow index readable", True)
        except IndexError as e:
            check("ObsFlow index readable", False, str(e).split("\n")[1] if "\n" in str(e) else str(e))
        except Exception as e:
            check("ObsFlow index readable", False, str(e))

    # 6. API ping (Haiku, 1 token)
    if api_key:
        try:
            resp = ai_core.call(
                task="ping",
                prompt="Reply with the single word: ok",
                max_tokens=5,
                command="doctor",
            )
            check(
                f"API ping succeeded (haiku, {resp.input_tokens}→{resp.output_tokens} tok, ${resp.cost_usd:.5f})",
                True,
            )
        except EnvironmentError as e:
            check("API ping", False, str(e).split("\n")[1] if "\n" in str(e) else str(e))
        except Exception as e:
            msg = str(e)
            if verbose:
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/dim]")
            check("API ping", False, f"Fix: check API key and network. {msg[:80]}")
    else:
        check("API ping (skipped — no API key)", False, "Fix: export ANTHROPIC_API_KEY=sk-ant-...")

    console.print()
    if all_ok:
        console.print(f"[green]✓ All checks passed.[/green]\n")
    else:
        console.print(f"[red]✗ Some checks failed. Fix the issues above and re-run obsmind doctor.[/red]\n")
        raise typer.Exit(1)


# ── profile ────────────────────────────────────────────────────────────────

profile_app = typer.Typer(help="Manage the active profile.")


@profile_app.command("show")
def profile_show() -> None:
    """Print the active profile name."""
    cfg = load_config()
    name = cfg.get("profile", "dev")
    console.print(f"[{INDIGO}]Active profile:[/{INDIGO}] {name}")


@profile_app.command("set")
def profile_set(name: str = typer.Argument(help="Profile name")) -> None:
    """Switch to a named profile."""
    if name not in PROFILES:
        console.print(f"[yellow]⚠  Only the dev profile is implemented.[/yellow]")
        console.print(f"[dim]  See profiles/README.md to add a new one.[/dim]")
        raise typer.Exit(1)
    cfg = load_config()
    cfg["profile"] = name
    save_config(cfg)
    console.print(f"[green]✓[/green] Profile set to '{name}'")
