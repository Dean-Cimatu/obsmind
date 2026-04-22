"""Command: obsmind view — render a vault note in the terminal."""

from typing import Annotated, Optional

import typer
from rich.console import Console

from ..core.render import render, glow_available
from ..core.vault import load_config, resolve_vault_path, find_note_fuzzy

console = Console()
DIM = "dim"


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)


def register(app: typer.Typer) -> None:
    @app.command("view")
    def cmd_view(
        note: Annotated[list[str], typer.Argument(help="Note name (fuzzy matched)")],
        rich_: Annotated[bool, typer.Option("--rich", help="Force Rich renderer")] = False,
        glow_: Annotated[bool, typer.Option("--glow", help="Force Glow renderer")] = False,
    ) -> None:
        """Render a vault note in the terminal. Auto-selects Rich or Glow."""
        query = " ".join(note)
        cfg = load_config()

        try:
            vault_path = resolve_vault_path(cfg)
        except FileNotFoundError as e:
            _die(str(e))

        path = find_note_fuzzy(vault_path, query)
        if path is None:
            _die(f"No note found matching '{query}'.")

        content = path.read_text()

        if rich_ and glow_:
            _die("--rich and --glow are mutually exclusive.")

        force = "rich" if rich_ else ("glow" if glow_ else "")

        if not force:
            from ..core.render import _should_use_glow
            using = "glow" if (_should_use_glow(content) and glow_available()) else "rich"
            console.print(f"[{DIM}]renderer: {using}[/{DIM}]\n")

        render(content, title=path.stem, force=force)
