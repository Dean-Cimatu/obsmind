"""Command: obsmind standup — generate a daily standup from yesterday's note."""

import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ..core import ai as ai_core
from ..core.context import load_context
from ..core.prompts import load as load_prompt
from ..core.vault import (
    load_config,
    resolve_vault_path,
    find_daily_notes,
    find_project_notes,
    read_note,
)

console = Console()
INDIGO = "bright_blue"
DIM    = "dim"


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)


def standup_command(days_back: int, copy: bool) -> None:
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    daily_folder = cfg.get("daily_notes_folder", "Daily Notes")
    today = datetime.today().strftime("%Y-%m-%d")

    # Find yesterday's note — walk back up to days_back days
    yesterday_content = ""
    yesterday_date    = ""
    for i in range(1, days_back + 1):
        dt   = datetime.today() - timedelta(days=i)
        date = dt.strftime("%Y-%m-%d")
        path = vault_path / daily_folder / f"{date}.md"
        if path.exists():
            try:
                _, body = read_note(path)
                yesterday_content = body.strip()
                yesterday_date    = date
            except Exception:
                pass
            break

    if not yesterday_content:
        _die(
            f"No daily note found in the last {days_back} days.\n"
            "  Create one with: obs daily"
        )

    # Collect open tasks from yesterday's note
    open_tasks = _extract_open_tasks(yesterday_content)

    # Recent project context
    project_paths   = find_project_notes(vault_path)
    project_context = _summarise_projects(project_paths[:4])

    user_ctx = load_context() or "(no context)"

    prompt_text = load_prompt(
        "standup",
        today=today,
        yesterday_note=f"### {yesterday_date}\n{yesterday_content[:2000]}",
        open_tasks=open_tasks or "(none)",
        project_context=project_context or "(none)",
        user_context=user_ctx[:400],
    )

    with console.status(f"[{DIM}]Generating standup from {yesterday_date}…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="standup",
                prompt=prompt_text,
                max_tokens=400,
                command="standup",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    standup_text = resp.content.strip()

    console.print()
    console.print(Panel(
        Markdown(standup_text),
        title=f"[{INDIGO}]Standup — {today}[/{INDIGO}]",
        border_style=INDIGO,
    ))
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")

    if copy:
        _copy_to_clipboard(standup_text)
        console.print(f"[green]✓[/green] Copied to clipboard\n")


# ── helpers ────────────────────────────────────────────────────────────────

def _extract_open_tasks(content: str) -> str:
    tasks = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]"):
            task = stripped[6:].strip()
            if task:
                tasks.append(f"- {task}")
    return "\n".join(tasks)


def _summarise_projects(paths: list) -> str:
    parts = []
    for p in paths:
        try:
            meta, body = read_note(p)
            title  = meta.get("title") or p.stem
            status = meta.get("status", "")
            preview = body.strip()[:200]
            parts.append(f"**{title}**{f' ({status})' if status else ''}: {preview}")
        except Exception:
            continue
    return "\n\n".join(parts)


def _copy_to_clipboard(text: str) -> None:
    """Copy text to clipboard using pbcopy (macOS) or xclip (Linux)."""
    if shutil.which("pbcopy"):
        subprocess.run(["pbcopy"], input=text.encode(), check=False)
    elif shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=False)
    else:
        console.print(f"[yellow]⚠[/yellow]  No clipboard tool found (pbcopy/xclip).")


# ── Typer registration ─────────────────────────────────────────────────────

def register(app: typer.Typer) -> None:
    @app.command("standup")
    def cmd_standup(
        days: Annotated[int, typer.Option("--days", "-d", help="How many days back to look for a note")] = 3,
        copy: Annotated[bool, typer.Option("--copy", "-c", help="Copy standup to clipboard")] = False,
    ) -> None:
        """Generate a daily standup from yesterday's note."""
        standup_command(days_back=days, copy=copy)
