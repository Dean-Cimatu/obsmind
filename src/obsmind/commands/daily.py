"""Commands: obsmind daily [--update] [--reflect] [--fill] + daily summary."""

import json
import re
import sys
from datetime import datetime
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.text import Text

from ..core import ai as ai_core
from ..core.context import system_prompt, load_context
from ..core.obsflow import daily_add, ObsFlowError, ObsFlowNotFoundError
from ..core.prompts import load as load_prompt
from ..core.sections import parse_sections, sections_prompt_block, extract_section
from ..core.vault import load_config, resolve_vault_path, read_today_note, find_daily_notes, read_note, find_project_notes

console = Console()

INDIGO = "bright_blue"
AMBER  = "yellow"
DIM    = "dim"

FALLBACK_SECTION = "Quick Capture"
CONFIDENCE_THRESHOLD = 0.7


# ── Typer app ──────────────────────────────────────────────────────────────

daily_app = typer.Typer(
    help="Surgical edits to today's daily note.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@daily_app.callback(invoke_without_command=True, context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def daily(
    ctx: typer.Context,
    update: Annotated[Optional[str], typer.Option("--update", "-u", help="Route text to the right section")] = None,
    reflect: Annotated[bool, typer.Option("--reflect", "-r", help="Interactive end-of-day reflection")] = False,
    fill: Annotated[bool, typer.Option("--fill", "-f", help="Suggest Focus Areas from context")] = False,
) -> None:
    """Interact with today's daily note via AI routing.

    With no flags, shows this help. Use --update, --reflect, or --fill.
    """
    if ctx.invoked_subcommand is not None:
        return

    # Collect any trailing unquoted words into --update
    if update and ctx.args:
        update = update + " " + " ".join(ctx.args)
    elif ctx.args and not update and not reflect and not fill:
        # bare words with no flag treated as --update
        update = " ".join(ctx.args)

    if update:
        _cmd_update(update)
    elif reflect:
        _cmd_reflect()
    elif fill:
        _cmd_fill()
    else:
        console.print(ctx.get_help())


@daily_app.command("summary")
def summary() -> None:
    """Print a structured summary of today's note. Read-only."""
    _cmd_summary()


# ── --update ───────────────────────────────────────────────────────────────

def _cmd_update(instruction: str) -> None:
    """Route text to the right section of today's daily note."""
    cfg = load_config()

    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    try:
        content, note_path = read_today_note(vault_path, cfg.get("daily_notes_folder", "Daily Notes"))
    except FileNotFoundError as e:
        _die(str(e))

    sections_block = sections_prompt_block(content)
    note_preview   = _note_preview(content, max_chars=1200)
    user_ctx       = load_context() or ""

    prompt_text = load_prompt(
        "daily_update",
        sections_list=sections_block,
        note_preview=note_preview,
        user_context=user_ctx[:800] if user_ctx else "(no context cached — run obsmind context update)",
        instruction=instruction,
    )

    console.print(f"\n[{DIM}]Routing to daily note…[/{DIM}]")

    try:
        resp = ai_core.call(
            task="daily_update",
            prompt=prompt_text,
            max_tokens=400,
            command="daily --update",
        )
    except (EnvironmentError, ValueError) as e:
        _die(str(e))
    except ObsFlowNotFoundError as e:
        _die(str(e))

    parsed = _parse_json_response(resp.content)
    if parsed is None:
        _die(f"AI returned unexpected response: {resp.content[:200]}")

    section    = parsed.get("section", FALLBACK_SECTION)
    text       = parsed.get("text", "")
    confidence = float(parsed.get("confidence", 1.0))
    fell_back  = False

    # Validate section exists in note
    known = {s.name for s in parse_sections(content)}
    if section not in known:
        section   = FALLBACK_SECTION
        confidence = 0.0
        fell_back  = True

    if confidence < CONFIDENCE_THRESHOLD:
        section   = FALLBACK_SECTION
        fell_back = True

    if not text.strip():
        _die("AI returned empty text. Try rephrasing.")

    # Diff preview
    _show_diff_preview(section, text, note_path)

    if fell_back:
        console.print(
            f"[{DIM}]No clear section — adding to Quick Capture. "
            f"Override with: obs append <section> \"{text}\"[/{DIM}]"
        )

    confirmed = Confirm.ask("\n  Confirm write?", default=False)
    if not confirmed:
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        raise typer.Exit(0)

    try:
        daily_add(section, text)
    except ObsFlowNotFoundError as e:
        _die(str(e))
    except ObsFlowError as e:
        _die(str(e))

    console.print(f"\n[green]✓[/green] Added to [bold]{section}[/bold]")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── --reflect ──────────────────────────────────────────────────────────────

def _cmd_reflect() -> None:
    """Interactive end-of-day reflection."""
    cfg = load_config()

    try:
        vault_path = resolve_vault_path(cfg)
        content, note_path = read_today_note(vault_path, cfg.get("daily_notes_folder", "Daily Notes"))
    except FileNotFoundError as e:
        _die(str(e))

    console.print(f"\n[{INDIGO}]ObsMind[/{INDIGO}] reflect  [{DIM}]{note_path.name}[/{DIM}]\n")

    prompts_q = [
        ("went_well",  "What went well today?"),
        ("improve",    "What could be improved?"),
        ("tomorrow",   "Tomorrow's priorities?"),
    ]
    answers: dict[str, str] = {}
    for key, question in prompts_q:
        console.print(f"  [{INDIGO}]{question}[/{INDIGO}]")
        try:
            answer = Prompt.ask("  →")
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[{DIM}]  Aborted.[/{DIM}]")
            raise typer.Exit(0)
        if not answer.strip():
            console.print(f"[{DIM}]  Skipped.[/{DIM}]")
            continue
        answers[key] = answer.strip()
        console.print()

    if not answers:
        console.print(f"[{DIM}]  Nothing to write.[/{DIM}]")
        return

    answers_block = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in answers.items())
    prompt_text = load_prompt(
        "daily_reflect",
        user_context=load_context() or "(no context)",
        note_preview=_note_preview(content, max_chars=600),
        answers=answers_block,
    )

    with console.status(f"[{DIM}]Formatting reflection…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="daily_reflect",
                prompt=prompt_text,
                max_tokens=600,
                command="daily --reflect",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    formatted = resp.content.strip()
    _show_diff_preview("Reflection", formatted, note_path)

    confirmed = Confirm.ask("\n  Confirm write?", default=False)
    if not confirmed:
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        return

    # Write each line separately so obs append handles them cleanly
    try:
        daily_add("Reflection", formatted)
    except ObsFlowError as e:
        _die(str(e))

    console.print(f"\n[green]✓[/green] Reflection written")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── --fill ─────────────────────────────────────────────────────────────────

def _cmd_fill() -> None:
    """Suggest Focus Areas entries from vault context."""
    cfg = load_config()

    try:
        vault_path = resolve_vault_path(cfg)
        content, note_path = read_today_note(vault_path, cfg.get("daily_notes_folder", "Daily Notes"))
    except FileNotFoundError as e:
        _die(str(e))

    # Gather context
    daily_folder = cfg.get("daily_notes_folder", "Daily Notes")
    recent = find_daily_notes(vault_path, daily_folder, days=3)
    recent_text = _summarise_recent_dailies(recent)

    project_paths = find_project_notes(vault_path)
    projects_text = _summarise_projects(project_paths[:5])

    todos_text = _extract_open_todos(content)

    prompt_text = load_prompt(
        "daily_fill",
        user_context=load_context() or "(no context)",
        projects_summary=projects_text or "(none found)",
        open_todos=todos_text or "(none found)",
        recent_dailies=recent_text or "(none found)",
    )

    with console.status(f"[{DIM}]Generating Focus Areas…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="daily_fill",
                prompt=prompt_text,
                max_tokens=400,
                command="daily --fill",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    suggestions = _parse_json_list(resp.content)
    if not suggestions:
        console.print(f"[yellow]⚠  No suggestions generated.[/yellow]")
        return

    console.print(f"\n[{INDIGO}]ObsMind[/{INDIGO}] Focus Areas suggestions\n")

    accepted: list[str] = []
    for i, suggestion in enumerate(suggestions, 1):
        console.print(f"  [{AMBER}]{i}. {suggestion}[/{AMBER}]")
        try:
            ok = Confirm.ask("     Accept?", default=True)
        except (KeyboardInterrupt, EOFError):
            break
        if ok:
            accepted.append(suggestion)
        console.print()

    if not accepted:
        console.print(f"[{DIM}]  Nothing accepted.[/{DIM}]")
        return

    console.print(f"  Adding {len(accepted)} entr{'y' if len(accepted) == 1 else 'ies'} to Focus Areas…\n")

    for entry in accepted:
        try:
            daily_add("Focus Areas", entry)
        except ObsFlowError as e:
            console.print(f"[red]✗[/red] Failed to write '{entry}': {e}")

    console.print(f"[green]✓[/green] Focus Areas updated")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── summary ────────────────────────────────────────────────────────────────

def _cmd_summary() -> None:
    """Print a structured summary of today's note. No writes."""
    cfg = load_config()

    try:
        vault_path = resolve_vault_path(cfg)
        content, note_path = read_today_note(vault_path, cfg.get("daily_notes_folder", "Daily Notes"))
    except FileNotFoundError as e:
        _die(str(e))

    prompt_text = load_prompt("daily_summary", note_content=content[:3000])

    with console.status(f"[{DIM}]Summarising…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="daily_summary",
                prompt=prompt_text,
                max_tokens=600,
                command="daily summary",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    today = datetime.today().strftime("%Y-%m-%d")
    console.print(Panel(
        resp.content.strip(),
        title=f"[{INDIGO}]Daily Summary — {today}[/{INDIGO}]",
        border_style=INDIGO,
    ))
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── helpers ────────────────────────────────────────────────────────────────

def _parse_json_response(text: str) -> dict | None:
    """Parse AI JSON response, stripping markdown fences if present."""
    # Strip ```json ... ``` fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # Find the first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _parse_json_list(text: str) -> list[str]:
    """Parse AI JSON array response."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        result = json.loads(match.group())
        return [str(s) for s in result if s]
    except json.JSONDecodeError:
        return []


def _note_preview(content: str, max_chars: int = 1000) -> str:
    """Trim a note to a reasonable preview length."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n…(truncated)"


def _show_diff_preview(section: str, text: str, note_path: object) -> None:
    """Render a clear before/after diff preview."""
    console.print(f"\n  [{DIM}]Section:[/{DIM}] [bold]{section}[/bold]")
    console.print(f"  [{DIM}]Note:   [/{DIM}] [{DIM}]{note_path}[/{DIM}]\n")

    for line in text.splitlines():
        console.print(f"  [green]+ {line}[/green]")


def _summarise_recent_dailies(dailies: list) -> str:
    parts = []
    for date_str, path in dailies:
        try:
            _, body = read_note(path)
            preview = body.strip()[:400]
            parts.append(f"### {date_str}\n{preview}")
        except Exception:
            pass
    return "\n\n".join(parts)


def _summarise_projects(paths: list) -> str:
    parts = []
    for p in paths:
        try:
            meta, body = read_note(p)
            title = meta.get("title") or p.stem
            parts.append(f"- [[{title}]]: {body.strip()[:200]}")
        except Exception:
            pass
    return "\n".join(parts)


def _extract_open_todos(note_content: str) -> str:
    """Extract open checkbox and table todos from the note content."""
    lines = []
    for line in note_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]"):
            lines.append(stripped[6:].strip())
        elif "| [ ] |" in stripped or "| [ ]|" in stripped:
            # table row — extract task text
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            if cells:
                lines.append(cells[0])
    return "\n".join(f"- {t}" for t in lines) if lines else ""


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)
