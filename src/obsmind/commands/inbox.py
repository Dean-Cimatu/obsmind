"""Command: obsmind inbox — process Quick Capture items from daily notes."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from ..core import ai as ai_core
from ..core.context import load_context
from ..core.obsflow import append_to_note, create_note, rewrite_note, ObsFlowError, ObsFlowNotFoundError
from ..core.prompts import load as load_prompt
from ..core.vault import (
    load_config,
    resolve_vault_path,
    find_daily_notes,
    iter_notes,
    read_note,
)

console = Console()
INDIGO = "bright_blue"
DIM    = "dim"
AMBER  = "yellow"

_PROCESSED_MARKER = "~~"   # strikethrough = processed


@dataclass
class CaptureItem:
    text: str
    date: str
    note_path: object   # Path to the daily note it came from
    line_index: int     # line number within the daily note body


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)


def inbox_command(days: int, dry_run: bool) -> None:
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    daily_folder = cfg.get("daily_notes_folder", "Daily Notes")

    # Collect unprocessed Quick Capture items
    with console.status(f"[{DIM}]Scanning last {days} days of Quick Capture…[/{DIM}]"):
        recent = find_daily_notes(vault_path, daily_folder, days=days)
        items  = _collect_captures(recent)

    if not items:
        console.print(f"[{DIM}]  Quick Capture is clear — nothing to process.[/{DIM}]\n")
        return

    console.print(f"\n  [{INDIGO}]ObsMind Inbox[/{INDIGO}]  [{DIM}]{len(items)} item{'s' if len(items) != 1 else ''} found[/{DIM}]\n")

    # Collect vault note titles for Claude
    all_titles = sorted({p.stem for p in iter_notes(vault_path)})
    titles_block = "\n".join(f"- {t}" for t in all_titles[:400])

    items_block = "\n".join(
        f"[{i.date}] {i.text}" for i in items
    )

    user_ctx = load_context() or "(no context)"

    prompt_text = load_prompt(
        "inbox_route",
        items=items_block,
        vault_notes=titles_block,
        user_context=user_ctx[:600],
    )

    with console.status(f"[{DIM}]Routing {len(items)} items…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="inbox_route",
                prompt=prompt_text,
                max_tokens=1500,
                command="inbox",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    routes = _parse_routes(resp.content)

    if not routes:
        _die(f"Could not parse routing response: {resp.content[:200]}")

    # Match routes back to items (by order)
    paired = list(zip(items, routes))

    # Show routing plan
    _show_routing_table(paired)
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")

    if dry_run:
        console.print(f"[{DIM}]  Dry run — no changes written.[/{DIM}]\n")
        return

    # Interactive processing
    processed_paths: dict = {}   # path -> set of line indices to mark done

    for item, route in paired:
        action      = route.get("action", "keep")
        destination = route.get("destination")
        reason      = route.get("reason", "")

        if action == "discard":
            console.print(f"\n  [{DIM}]Discard:[/{DIM}] {item.text[:80]}")
            console.print(f"  [{DIM}]{reason}[/{DIM}]")
            try:
                ok = Confirm.ask("  Discard?", default=True)
            except (KeyboardInterrupt, EOFError):
                break
            if ok:
                _mark_processed(processed_paths, item)
            continue

        if action == "keep":
            console.print(f"\n  [{DIM}]Keep in daily:[/{DIM}] {item.text[:80]}")
            continue

        if action == "append" and destination:
            console.print(f"\n  [green]→ [[{destination}]][/green]  {item.text[:70]}")
            console.print(f"  [{DIM}]{reason}[/{DIM}]")
            try:
                ok = Confirm.ask("  Route here?", default=True)
            except (KeyboardInterrupt, EOFError):
                break
            if ok:
                try:
                    append_to_note(destination, item.text)
                    _mark_processed(processed_paths, item)
                    console.print(f"  [green]✓[/green] Appended to [bold]{destination}[/bold]")
                except (ObsFlowError, ObsFlowNotFoundError) as e:
                    console.print(f"  [red]✗[/red] {e}")
            continue

        if action == "create" and destination:
            console.print(f"\n  [yellow]+[/yellow] Create new note: [bold]{destination}[/bold]")
            console.print(f"  Content: {item.text[:80]}")
            console.print(f"  [{DIM}]{reason}[/{DIM}]")
            try:
                ok = Confirm.ask("  Create note?", default=True)
            except (KeyboardInterrupt, EOFError):
                break
            if ok:
                note_content = f"# {destination}\n\n{item.text}\n"
                try:
                    create_note(destination, note_content)
                    _mark_processed(processed_paths, item)
                    console.print(f"  [green]✓[/green] Created [bold]{destination}[/bold]")
                except (ObsFlowError, ObsFlowNotFoundError) as e:
                    console.print(f"  [red]✗[/red] {e}")

    # Write strikethrough markers back to daily notes
    _flush_processed(processed_paths)

    console.print()


# ── helpers ────────────────────────────────────────────────────────────────

def _collect_captures(daily_notes: list) -> list[CaptureItem]:
    """Extract unprocessed lines from Quick Capture sections."""
    items = []
    _QC_HEADER = re.compile(r"^## Quick Capture", re.IGNORECASE)
    _NEXT_H2   = re.compile(r"^## ", re.MULTILINE)

    for date_str, path in daily_notes:
        try:
            _, body = read_note(path)
        except Exception:
            continue

        lines = body.splitlines()
        in_qc = False
        for i, line in enumerate(lines):
            if _QC_HEADER.match(line):
                in_qc = True
                continue
            if in_qc and _NEXT_H2.match(line):
                break
            if not in_qc:
                continue

            stripped = line.strip()
            # Skip empty lines, already processed (strikethrough), headers
            if not stripped:
                continue
            if stripped.startswith(_PROCESSED_MARKER) and stripped.endswith(_PROCESSED_MARKER):
                continue
            if stripped.startswith("#"):
                continue
            # Strip leading bullet markers
            text = re.sub(r"^[-*+]\s+", "", stripped).strip()
            if len(text) < 3:
                continue

            items.append(CaptureItem(text=text, date=date_str, note_path=path, line_index=i))

    return items


def _show_routing_table(paired: list) -> None:
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Date",   style=DIM,    width=12)
    table.add_column("Item",   style="bold", min_width=30)
    table.add_column("Action", width=8)
    table.add_column("Destination", style=AMBER)

    action_style = {
        "append":  "green",
        "create":  "yellow",
        "keep":    "dim",
        "discard": "red",
    }

    for item, route in paired:
        action = route.get("action", "keep")
        dest   = route.get("destination") or ""
        colour = action_style.get(action, "white")
        table.add_row(
            item.date,
            item.text[:50] + ("…" if len(item.text) > 50 else ""),
            f"[{colour}]{action}[/{colour}]",
            dest,
        )

    console.print(table)
    console.print()


def _mark_processed(processed_paths: dict, item: CaptureItem) -> None:
    key = str(item.note_path)
    if key not in processed_paths:
        processed_paths[key] = {"path": item.note_path, "indices": set()}
    processed_paths[key]["indices"].add(item.line_index)


def _flush_processed(processed_paths: dict) -> None:
    """Mark processed items with strikethrough in their daily notes."""
    for key, info in processed_paths.items():
        path    = info["path"]
        indices = info["indices"]
        if not indices:
            continue
        try:
            _, body = read_note(path)
            lines   = body.splitlines()
            for i in indices:
                if i < len(lines):
                    stripped = lines[i].strip()
                    bullet   = re.match(r"^([-*+]\s+)", lines[i])
                    prefix   = bullet.group(1) if bullet else ""
                    content  = re.sub(r"^[-*+]\s+", "", lines[i].strip())
                    if not (content.startswith("~~") and content.endswith("~~")):
                        lines[i] = f"{prefix}~~{content}~~"
            new_body = "\n".join(lines)
            rewrite_note(path.stem, new_body)
        except Exception:
            pass


def _parse_routes(text: str) -> list[dict]:
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match   = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        result = json.loads(match.group())
        return [r for r in result if isinstance(r, dict)]
    except json.JSONDecodeError:
        return []


# ── Typer registration ─────────────────────────────────────────────────────

def register(app: typer.Typer) -> None:
    @app.command("inbox")
    def cmd_inbox(
        days: Annotated[int, typer.Option("--days", "-d", help="Days of daily notes to scan")] = 7,
        dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Show routing plan without writing")] = False,
    ) -> None:
        """Process Quick Capture items — route each one to the right note."""
        inbox_command(days=days, dry_run=dry_run)
