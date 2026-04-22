"""Command: obsmind generate — create a new vault note from scratch."""

from datetime import datetime
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.syntax import Syntax

from ..core import ai as ai_core
from ..core.context import load_context
from ..core.obsflow import create_note, ObsFlowError, ObsFlowNotFoundError
from ..core.prompts import load as load_prompt
from ..core.retrieval import retrieve, format_for_prompt
from ..core.vault import load_config, resolve_vault_path

console = Console()

INDIGO = "bright_blue"
DIM    = "dim"


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)


def generate_command(
    title: str,
    instruction: str,
    folder: str,
    dry_run: bool,
) -> None:
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    # Check note doesn't already exist
    target_path = vault_path / (f"{folder}/" if folder else "") / f"{title}.md"
    if target_path.exists():
        _die(f"Note '{title}' already exists at {target_path.relative_to(vault_path)}.\n"
             "  Use 'obsmind note rewrite --full' to rewrite an existing note.")

    with console.status(f"[{DIM}]Finding related notes…[/{DIM}]"):
        related = retrieve(vault_path, f"{title} {instruction}", limit=4)

    related_block = format_for_prompt(related, max_chars_each=400)
    today = datetime.today().strftime("%Y-%m-%d")
    user_ctx = load_context() or "(no context)"

    prompt_text = load_prompt(
        "generate",
        title=title,
        user_context=user_ctx[:600],
        related_notes=related_block,
        instruction=instruction,
        today=today,
    )

    with console.status(f"[{DIM}]Generating '{title}'…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="generate",
                prompt=prompt_text,
                max_tokens=3000,
                command="generate",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    note_content = resp.content.strip()
    if not note_content:
        _die("AI returned empty note content.")

    console.print(f"\n  [{INDIGO}]ObsMind[/{INDIGO}] generate  [{DIM}]{title}.md[/{DIM}]\n")
    console.print(Syntax(note_content[:1200], "markdown", theme="monokai", word_wrap=True))

    if note_content and len(note_content) > 1200:
        console.print(f"  [{DIM}]…({len(note_content)} chars total)[/{DIM}]")

    if dry_run:
        console.print(f"\n  [{DIM}]Dry run — no note created.[/{DIM}]")
        console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")
        return

    folder_display = f" in {folder}/" if folder else ""
    try:
        confirmed = Confirm.ask(f"\n  Create note '{title}'{folder_display}?", default=False)
    except (KeyboardInterrupt, EOFError):
        confirmed = False

    if not confirmed:
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        raise typer.Exit(0)

    try:
        create_note(title, note_content, folder=folder)
    except ObsFlowNotFoundError as e:
        _die(str(e))
    except ObsFlowError as e:
        _die(str(e))

    console.print(f"\n[green]✓[/green] Created [bold]{title}.md[/bold]{folder_display}")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── Typer registration ─────────────────────────────────────────────────────

def register(app: typer.Typer) -> None:
    @app.command("generate")
    def cmd_generate(
        title: Annotated[str, typer.Argument(help="Title for the new note")],
        instruction: Annotated[str, typer.Option("--instruction", "-i", help="What the note should cover")],
        folder: Annotated[str, typer.Option("--folder", "-f", help="Subfolder within vault")] = "",
        dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview without creating")] = False,
    ) -> None:
        """Generate a new vault note from scratch using Opus."""
        generate_command(title=title, instruction=instruction, folder=folder, dry_run=dry_run)
