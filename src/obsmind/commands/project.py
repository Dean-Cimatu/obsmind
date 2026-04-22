"""Command: obsmind project — project status brief from vault notes."""

import re
from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ..core import ai as ai_core
from ..core.context import load_context
from ..core.prompts import load as load_prompt
from ..core.retrieval import retrieve, format_for_prompt
from ..core.vault import (
    load_config,
    resolve_vault_path,
    find_note_fuzzy,
    find_daily_notes,
    read_note,
    iter_notes,
)

console = Console()
INDIGO = "bright_blue"
DIM    = "dim"
AMBER  = "yellow"


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)


def project_command(query: str, days: int) -> None:
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    # Resolve the project note
    note_path = find_note_fuzzy(vault_path, query)
    if note_path is None:
        _die(f"No note found matching '{query}'.\n  Try: obsmind find {query}")

    try:
        meta, body = read_note(note_path)
    except Exception as e:
        _die(f"Could not read note: {e}")

    project_note = note_path.read_text()
    project_name = note_path.stem
    today = datetime.today().strftime("%Y-%m-%d")

    # Scan daily notes for mentions of this project
    with console.status(f"[{DIM}]Scanning {days} days of daily notes…[/{DIM}]"):
        daily_folder  = cfg.get("daily_notes_folder", "Daily Notes")
        recent        = find_daily_notes(vault_path, daily_folder, days=days)
        daily_mentions = _find_mentions(project_name, recent)

    # Related notes via retrieval
    with console.status(f"[{DIM}]Finding related notes…[/{DIM}]"):
        related = retrieve(vault_path, f"{project_name} {body[:200]}", limit=4)
        # exclude the project note itself
        related = [r for r in related if r.path != note_path]
        related_block = format_for_prompt(related, max_chars_each=300)

    prompt_text = load_prompt(
        "project_status",
        project_note=project_note[:3000],
        daily_mentions=daily_mentions or "(no mentions in recent daily notes)",
        related_notes=related_block,
        today=today,
    )

    with console.status(f"[{DIM}]Generating project brief…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="project_status",
                prompt=prompt_text,
                max_tokens=800,
                command="project",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    status_line = _extract_status(resp.content)
    status_colour = {
        "active":   "green",
        "stalled":  "yellow",
        "planned":  "blue",
        "complete": "dim",
    }.get(status_line.lower(), INDIGO)

    console.print()
    console.print(Panel(
        Markdown(resp.content.strip()),
        title=f"[{INDIGO}]{project_name}[/{INDIGO}]  [{status_colour}]{status_line}[/{status_colour}]",
        border_style=INDIGO,
    ))
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── helpers ────────────────────────────────────────────────────────────────

def _find_mentions(project_name: str, daily_notes: list) -> str:
    """Extract lines from daily notes that mention the project by name."""
    name_re = re.compile(re.escape(project_name), re.IGNORECASE)
    blocks  = []

    for date_str, path in daily_notes:
        try:
            _, body = read_note(path)
        except Exception:
            continue

        matching = [
            line.strip()
            for line in body.splitlines()
            if name_re.search(line) and line.strip()
        ]

        if matching:
            excerpt = "\n".join(f"  {l}" for l in matching[:6])
            blocks.append(f"### {date_str}\n{excerpt}")

    return "\n\n".join(blocks)


def _extract_status(content: str) -> str:
    """Pull the Status value from the generated brief."""
    m = re.search(r"\*\*Status\*\*\s*[—–-]\s*(\w+)", content)
    return m.group(1).capitalize() if m else "Unknown"


# ── Typer registration ─────────────────────────────────────────────────────

def register(app: typer.Typer) -> None:
    @app.command("project")
    def cmd_project(
        name: Annotated[list[str], typer.Argument(help="Project note name (fuzzy matched)")],
        days: Annotated[int, typer.Option("--days", "-d", help="Days of daily notes to scan for mentions")] = 30,
    ) -> None:
        """Generate a project status brief from the project note and daily mentions."""
        project_command(" ".join(name), days=days)
