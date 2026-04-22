"""Commands: obsmind review + obsmind prioritise."""

import re
from datetime import datetime
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..core import ai as ai_core
from ..core.context import load_context
from ..core.prompts import load as load_prompt
from ..core.vault import (
    load_config,
    resolve_vault_path,
    find_daily_notes,
    find_project_notes,
    iter_notes,
    read_note,
)

console = Console()

INDIGO = "bright_blue"
DIM    = "dim"


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)


# ── review ─────────────────────────────────────────────────────────────────

def review_command(days: int) -> None:
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    daily_folder = cfg.get("daily_notes_folder", "Daily Notes")

    with console.status(f"[{DIM}]Gathering last {days} days…[/{DIM}]"):
        recent = find_daily_notes(vault_path, daily_folder, days=days)
        project_paths = find_project_notes(vault_path)

    if not recent:
        _die(f"No daily notes found in the last {days} days.")

    daily_block = _build_daily_block(recent)
    projects_block = _build_projects_block(project_paths[:6])
    user_ctx = load_context() or "(no context cached — run obsmind context update)"

    prompt_text = load_prompt(
        "review",
        user_context=user_ctx[:600],
        daily_notes=daily_block,
        projects=projects_block or "(none found)",
    )

    console.print(f"\n  [{INDIGO}]ObsMind[/{INDIGO}] weekly review  [{DIM}]last {days} days[/{DIM}]\n")

    full_text = ""
    try:
        for chunk in ai_core.stream(
            task="review",
            prompt=prompt_text,
            max_tokens=2000,
            command="review",
        ):
            console.print(chunk, end="")
            full_text += chunk
    except (EnvironmentError, ValueError) as e:
        _die(str(e))

    console.print("\n")


# ── prioritise ─────────────────────────────────────────────────────────────

def prioritise_command(days: int) -> None:
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    daily_folder = cfg.get("daily_notes_folder", "Daily Notes")

    with console.status(f"[{DIM}]Scanning vault for open tasks…[/{DIM}]"):
        tasks = _collect_open_tasks(vault_path, daily_folder, days=days)

    if not tasks:
        console.print(f"[{DIM}]  No open tasks found.[/{DIM}]")
        return

    today = datetime.today().strftime("%Y-%m-%d")
    user_ctx = load_context() or "(no context)"

    prompt_text = load_prompt(
        "prioritise",
        user_context=user_ctx[:600],
        open_tasks=tasks,
        today=today,
    )

    with console.status(f"[{DIM}]Ranking {tasks.count(chr(10)) + 1} tasks…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="prioritise",
                prompt=prompt_text,
                max_tokens=1000,
                command="prioritise",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    console.print(Panel(
        resp.content.strip(),
        title=f"[{INDIGO}]Priority List — {today}[/{INDIGO}]",
        border_style=INDIGO,
    ))
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── helpers ────────────────────────────────────────────────────────────────

def _build_daily_block(daily_notes: list) -> str:
    parts = []
    for date_str, path in daily_notes:
        try:
            _, body = read_note(path)
            preview = body.strip()[:600]
            parts.append(f"### {date_str}\n{preview}")
        except Exception:
            continue
    return "\n\n".join(parts)


def _build_projects_block(paths: list) -> str:
    parts = []
    for p in paths:
        try:
            meta, body = read_note(p)
            title = meta.get("title") or p.stem
            parts.append(f"- [[{title}]]: {body.strip()[:250]}")
        except Exception:
            continue
    return "\n".join(parts)


def _collect_open_tasks(vault_path, daily_folder: str, days: int) -> str:
    """Collect all open checkbox tasks from recent daily notes and all vault notes."""
    tasks: list[str] = []

    # From recent daily notes — labelled with date
    recent = find_daily_notes(vault_path, daily_folder, days=days)
    for date_str, path in recent:
        try:
            _, body = read_note(path)
            for line in body.splitlines():
                stripped = line.strip()
                if stripped.startswith("- [ ]"):
                    task_text = stripped[6:].strip()
                    if task_text:
                        tasks.append(f"[Daily {date_str}] {task_text}")
        except Exception:
            continue

    # From project notes
    for p in find_project_notes(vault_path):
        try:
            _, body = read_note(p)
            for line in body.splitlines():
                stripped = line.strip()
                if stripped.startswith("- [ ]"):
                    task_text = stripped[6:].strip()
                    if task_text:
                        tasks.append(f"[{p.stem}] {task_text}")
        except Exception:
            continue

    return "\n".join(f"- {t}" for t in tasks)


# ── Typer registration ─────────────────────────────────────────────────────

def register(app: typer.Typer) -> None:
    @app.command("review")
    def cmd_review(
        days: Annotated[int, typer.Option("--days", "-d", help="Days of history to include")] = 7,
    ) -> None:
        """Generate a structured weekly review from recent daily notes and projects."""
        review_command(days=days)

    @app.command("prioritise")
    def cmd_prioritise(
        days: Annotated[int, typer.Option("--days", "-d", help="Days of daily notes to scan")] = 14,
    ) -> None:
        """Rank open tasks from your vault by urgency and importance."""
        prioritise_command(days=days)
