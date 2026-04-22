"""Command: obsmind connect — find conceptually related unlinked notes."""

import json
import re
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from ..core import ai as ai_core
from ..core.obsflow import rewrite_note, ObsFlowError, ObsFlowNotFoundError
from ..core.prompts import load as load_prompt
from ..core.retrieval import retrieve
from ..core.vault import load_config, resolve_vault_path, find_note_fuzzy, read_note

console = Console()
INDIGO = "bright_blue"
DIM    = "dim"
AMBER  = "yellow"

# Regex to extract [[wikilink]] targets from note content
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]")


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)


def connect_command(query: str, limit: int, apply: bool) -> None:
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    note_path = find_note_fuzzy(vault_path, query)
    if note_path is None:
        _die(f"No note found matching '{query}'.")

    content = note_path.read_text()
    note_name = note_path.stem

    try:
        meta, body = read_note(note_path)
    except Exception as e:
        _die(f"Could not read note: {e}")

    # Extract already-linked notes so Claude doesn't suggest them
    existing_links = {m.group(1).strip().lower() for m in _WIKILINK_RE.finditer(content)}
    existing_block = "\n".join(f"- {l}" for l in sorted(existing_links)) or "(none)"

    # Wide retrieval net — more candidates = better coverage
    with console.status(f"[{DIM}]Scanning vault for candidates…[/{DIM}]"):
        candidates = retrieve(vault_path, f"{note_name} {body[:300]}", limit=limit * 3)
        candidates = [c for c in candidates if c.path != note_path]

    if not candidates:
        console.print(f"[{DIM}]  No candidates found in vault.[/{DIM}]")
        return

    # Build candidate block with previews for Claude to reason about
    candidates_block = _build_candidates_block(candidates, max_per=250)

    prompt_text = load_prompt(
        "connect",
        note_title=note_name,
        note_content=content[:2500],
        existing_links=existing_block,
        candidates=candidates_block,
    )

    with console.status(f"[{DIM}]Finding connections across {len(candidates)} candidates…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="connect",
                prompt=prompt_text,
                max_tokens=1000,
                command="connect",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    connections = _parse_connections(resp.content)

    if not connections:
        console.print(f"\n  [{DIM}]No meaningful connections found for '{note_name}'.[/{DIM}]\n")
        return

    # Display results table
    console.print(f"\n  [{INDIGO}]Connections found for[/{INDIGO}] [bold]{note_name}[/bold]\n")

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Note",   style="bold", min_width=20)
    table.add_column("Why connected", style=DIM)
    table.add_column("Link target", style=AMBER, min_width=16)

    for c in connections[:limit]:
        title    = c.get("title", "")
        reason   = c.get("reason", "")
        suggest  = c.get("suggested_text") or "(add as reference)"
        table.add_row(title, reason, suggest)

    console.print(table)
    console.print(f"\n[{DIM}]  {resp.meta_line()}[/{DIM}]\n")

    if not apply:
        console.print(f"  [{DIM}]Run with --apply to add these links to '{note_name}'.[/{DIM}]\n")
        return

    # Apply: inject wikilinks or append references
    _apply_connections(connections[:limit], content, note_path, note_name)


def _apply_connections(
    connections: list[dict],
    content: str,
    note_path,
    note_name: str,
) -> None:
    """Add wikilinks to the note for each accepted connection."""
    new_content = content
    applied     = []
    appended    = []

    for c in connections:
        title       = c.get("title", "")
        suggest     = c.get("suggested_text")
        reason      = c.get("reason", "")

        console.print(f"\n  [{INDIGO}]→ [[{title}]][/{INDIGO}]")
        console.print(f"  [{DIM}]{reason}[/{DIM}]")

        try:
            ok = Confirm.ask("  Add this link?", default=True)
        except (KeyboardInterrupt, EOFError):
            break

        if not ok:
            continue

        if suggest and suggest in new_content and f"[[{title}]]" not in new_content:
            # Inline: replace the first occurrence of the suggested text
            new_content = new_content.replace(suggest, f"[[{title}|{suggest}]]", 1)
            applied.append(title)
        else:
            # Append as a reference at the end of the note
            appended.append(title)

    if not applied and not appended:
        console.print(f"\n[{DIM}]  Nothing added.[/{DIM}]\n")
        return

    # Add appended links as a See also section if they exist
    if appended:
        refs = "\n".join(f"- [[{t}]]" for t in appended)
        if "## See also" in new_content or "## Related" in new_content:
            # Append to existing section
            for header in ("## See also", "## Related"):
                if header in new_content:
                    new_content = new_content.replace(header, f"{header}\n{refs}", 1)
                    break
        else:
            new_content = new_content.rstrip() + f"\n\n## See also\n{refs}\n"

    console.print(f"\n  [{DIM}]Preview:[/{DIM}]")
    for t in applied:
        console.print(f"  [green]+ [[{t}]][/green] (inline)")
    for t in appended:
        console.print(f"  [green]+ [[{t}]][/green] (See also)")

    try:
        confirmed = Confirm.ask("\n  Write links to note?", default=False)
    except (KeyboardInterrupt, EOFError):
        confirmed = False

    if not confirmed:
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        return

    try:
        rewrite_note(note_name, new_content)
    except (ObsFlowError, ObsFlowNotFoundError) as e:
        _die(str(e))

    total = len(applied) + len(appended)
    console.print(f"\n[green]✓[/green] {total} link{'s' if total != 1 else ''} added to [bold]{note_name}[/bold]\n")


# ── helpers ────────────────────────────────────────────────────────────────

def _build_candidates_block(candidates: list, max_per: int = 250) -> str:
    parts = []
    for c in candidates:
        try:
            _, body = read_note(c.path)
            preview = body.strip()[:max_per]
        except Exception:
            preview = "(unreadable)"
        parts.append(f"### {c.title}\n{preview}")
    return "\n\n".join(parts)


def _parse_connections(text: str) -> list[dict]:
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match   = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        result = json.loads(match.group())
        return [r for r in result if isinstance(r, dict) and "title" in r]
    except json.JSONDecodeError:
        return []


# ── Typer registration ─────────────────────────────────────────────────────

def register(app: typer.Typer) -> None:
    @app.command("connect")
    def cmd_connect(
        note: Annotated[list[str], typer.Argument(help="Note name (fuzzy matched)")],
        limit: Annotated[int, typer.Option("--limit", "-l", help="Max connections to show")] = 8,
        apply: Annotated[bool, typer.Option("--apply", help="Interactively add links to the note")] = False,
    ) -> None:
        """Find conceptually related vault notes that should be linked but aren't."""
        connect_command(" ".join(note), limit=limit, apply=apply)
