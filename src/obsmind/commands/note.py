"""Commands: obsmind note edit/extend/enhance/rewrite/fix/tags/summarise."""

import json
import re
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm

from ..core import ai as ai_core
from ..core.context import load_context
from ..core.obsflow import rewrite_note, ObsFlowError, ObsFlowNotFoundError
from ..core.prompts import load as load_prompt
from ..core.sections import (
    parse_sections,
    sections_prompt_block,
    extract_section,
    replace_section_content,
    insert_section_after,
    list_sections,
)
from ..core.vault import load_config, resolve_vault_path, find_note_fuzzy, read_note, iter_notes

console = Console()

INDIGO = "bright_blue"
AMBER  = "yellow"
DIM    = "dim"


# ── Typer app ──────────────────────────────────────────────────────────────

note_app = typer.Typer(
    help="AI-powered note editing commands.",
    no_args_is_help=True,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _resolve_note(query: str) -> tuple:
    """Resolve a note by fuzzy name. Returns (content, path, meta)."""
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    path = find_note_fuzzy(vault_path, query)
    if path is None:
        _die(f"No note found matching '{query}'.")

    try:
        meta, body = read_note(path)
    except Exception as e:
        _die(f"Could not read note: {e}")

    # Reconstruct full content including frontmatter
    raw_content = path.read_text()
    return raw_content, path, meta


def _show_note_diff(note_path, old_content: str, new_content: str, label: str = "Changes") -> None:
    """Show a before/after diff summary."""
    old_lines = set(old_content.splitlines())
    new_lines  = set(new_content.splitlines())
    added   = [l for l in new_content.splitlines() if l not in old_lines and l.strip()]
    removed = [l for l in old_content.splitlines() if l not in new_lines and l.strip()]

    console.print(f"\n  [{DIM}]Note:[/{DIM}] [{DIM}]{note_path}[/{DIM}]")
    console.print(f"  [{DIM}]{label}:[/{DIM}]\n")

    shown = 0
    for line in removed[:8]:
        console.print(f"  [red]- {line[:120]}[/red]")
        shown += 1
    for line in added[:8]:
        console.print(f"  [green]+ {line[:120]}[/green]")
        shown += 1
    if shown == 0:
        console.print(f"  [{DIM}](whitespace/structural changes only)[/{DIM}]")


def _confirm_write(note_path, old_content: str, new_content: str, label: str = "Changes") -> bool:
    _show_note_diff(note_path, old_content, new_content, label)
    try:
        return Confirm.ask("\n  Confirm write?", default=False)
    except (KeyboardInterrupt, EOFError):
        return False


def _write_note(note_path, note_name: str, new_content: str) -> None:
    try:
        rewrite_note(note_name, new_content)
    except ObsFlowNotFoundError as e:
        _die(str(e))
    except ObsFlowError as e:
        _die(str(e))


def _parse_json_obj(text: str) -> dict | None:
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _parse_json_list(text: str) -> list:
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return []


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)


def _note_preview(content: str, max_chars: int = 1500) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n…(truncated)"


# ── edit ───────────────────────────────────────────────────────────────────

@note_app.command("edit")
def cmd_edit(
    note: Annotated[str, typer.Argument(help="Note name (fuzzy matched)")],
    section: Annotated[str, typer.Option("--section", "-s", help="Section to edit")],
    instruction: Annotated[str, typer.Option("--instruction", "-i", help="What to do")],
) -> None:
    """Surgically edit a specific section of a note."""
    content, path, meta = _resolve_note(note)
    note_name = path.stem

    section_content = extract_section(content, section)
    if section_content is None:
        available = [s.name for s in parse_sections(content)]
        _die(
            f"Section '{section}' not found in '{note_name}'.\n"
            f"  Available: {', '.join(available) or '(none)'}"
        )

    prompt_text = load_prompt(
        "edit",
        section_name=section,
        section_content=section_content.strip(),
        note_preview=_note_preview(content, 1200),
        user_context=load_context() or "(no context)",
        instruction=instruction,
    )

    with console.status(f"[{DIM}]Editing section '{section}'…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="note_edit",
                prompt=prompt_text,
                max_tokens=1200,
                command=f"note edit",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    new_body = resp.content.strip()
    new_content = replace_section_content(content, section, new_body)

    if not _confirm_write(path, content, new_content, f"Section: {section}"):
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        raise typer.Exit(0)

    _write_note(path, note_name, new_content)
    console.print(f"\n[green]✓[/green] Section [bold]{section}[/bold] updated in [bold]{note_name}[/bold]")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── extend ─────────────────────────────────────────────────────────────────

@note_app.command("extend")
def cmd_extend(
    note: Annotated[str, typer.Argument(help="Note name (fuzzy matched)")],
    section: Annotated[str, typer.Option("--section", "-s", help="Name of new section to add")],
    instruction: Annotated[Optional[str], typer.Option("--instruction", "-i", help="Guidance for content")] = None,
) -> None:
    """Add a new section to a note with AI-generated content."""
    content, path, meta = _resolve_note(note)
    note_name = path.stem

    sections_block = sections_prompt_block(content)

    prompt_text = load_prompt(
        "extend",
        sections_list=sections_block,
        note_preview=_note_preview(content, 1200),
        new_section_name=section,
        instruction=instruction or "Use context and note content to write relevant starter content.",
        user_context=load_context() or "(no context)",
    )

    with console.status(f"[{DIM}]Generating section '{section}'…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="note_extend",
                prompt=prompt_text,
                max_tokens=1000,
                command="note extend",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    parsed = _parse_json_obj(resp.content)
    if parsed is None:
        _die(f"AI returned unexpected response: {resp.content[:200]}")

    after_section = parsed.get("after_section", "end")
    new_body      = parsed.get("content", "").strip()

    if not new_body:
        _die("AI returned empty section content.")

    if after_section == "end":
        new_content = insert_section_after(content, "", section, new_body)
    else:
        new_content = insert_section_after(content, after_section, section, new_body)

    if not _confirm_write(path, content, new_content, f"New section: {section}"):
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        raise typer.Exit(0)

    _write_note(path, note_name, new_content)
    console.print(f"\n[green]✓[/green] Section [bold]{section}[/bold] added to [bold]{note_name}[/bold]")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── enhance ────────────────────────────────────────────────────────────────

@note_app.command("enhance")
def cmd_enhance(
    note: Annotated[str, typer.Argument(help="Note name (fuzzy matched)")],
) -> None:
    """Fill incomplete sections and add missing frontmatter. Never removes content."""
    content, path, meta = _resolve_note(note)
    note_name = path.stem

    prompt_text = load_prompt(
        "enhance",
        note_content=content,
        user_context=load_context() or "(no context)",
    )

    with console.status(f"[{DIM}]Enhancing '{note_name}'…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="note_enhance",
                prompt=prompt_text,
                max_tokens=3000,
                command="note enhance",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    new_content = resp.content.strip()
    if not new_content:
        _die("AI returned empty note.")

    if not _confirm_write(path, content, new_content, "Enhanced note"):
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        raise typer.Exit(0)

    _write_note(path, note_name, new_content)
    console.print(f"\n[green]✓[/green] [bold]{note_name}[/bold] enhanced")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── rewrite ────────────────────────────────────────────────────────────────

@note_app.command("rewrite")
def cmd_rewrite(
    note: Annotated[str, typer.Argument(help="Note name (fuzzy matched)")],
    instruction: Annotated[str, typer.Option("--instruction", "-i", help="How to rewrite")],
    section: Annotated[Optional[str], typer.Option("--section", "-s", help="Rewrite only this section")] = None,
    full: Annotated[bool, typer.Option("--full", help="Rewrite the entire note (uses Opus)")] = False,
) -> None:
    """Rewrite a section or entire note per instruction."""
    content, path, meta = _resolve_note(note)
    note_name = path.stem

    if full and section:
        _die("--full and --section are mutually exclusive.")

    if full:
        task     = "note_rewrite_full"
        scope    = "the entire note"
        target   = content
        scope_rule = "- Return the complete note including frontmatter."
    elif section:
        task      = "note_rewrite"
        scope     = f"the '{section}' section"
        sec_content = extract_section(content, section)
        if sec_content is None:
            available = [s.name for s in parse_sections(content)]
            _die(
                f"Section '{section}' not found.\n"
                f"  Available: {', '.join(available) or '(none)'}"
            )
        target     = sec_content.strip()
        scope_rule = "- Return ONLY the rewritten section body — no ## header, no surrounding content."
    else:
        _die("Specify --section <name> or --full.")

    prompt_text = load_prompt(
        "rewrite",
        scope=scope,
        content=target,
        note_preview=_note_preview(content, 1000),
        user_context=load_context() or "(no context)",
        instruction=instruction,
        scope_rule=scope_rule,
    )

    with console.status(f"[{DIM}]Rewriting {scope}…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task=task,
                prompt=prompt_text,
                max_tokens=4000 if full else 2000,
                command="note rewrite",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    rewritten = resp.content.strip()
    if not rewritten:
        _die("AI returned empty content.")

    if full:
        new_content = rewritten
    else:
        new_content = replace_section_content(content, section, rewritten)

    if not _confirm_write(path, content, new_content, f"Rewrite: {scope}"):
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        raise typer.Exit(0)

    _write_note(path, note_name, new_content)
    console.print(f"\n[green]✓[/green] Rewrote {scope} in [bold]{note_name}[/bold]")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── fix ────────────────────────────────────────────────────────────────────

@note_app.command("fix")
def cmd_fix(
    note: Annotated[str, typer.Argument(help="Note name (fuzzy matched)")],
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Show diff without writing")] = False,
) -> None:
    """Fix structural issues: heading hierarchy, frontmatter schema, bullet style."""
    content, path, meta = _resolve_note(note)
    note_name = path.stem

    prompt_text = load_prompt("fix", note_content=content)

    with console.status(f"[{DIM}]Checking structure of '{note_name}'…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="note_fix",
                prompt=prompt_text,
                max_tokens=3000,
                command="note fix",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    new_content = resp.content.strip()
    if not new_content:
        _die("AI returned empty note.")

    if new_content == content.strip():
        console.print(f"[{DIM}]  No structural issues found in '{note_name}'.[/{DIM}]")
        return

    _show_note_diff(path, content, new_content, "Structural fixes")

    if dry_run:
        console.print(f"\n[{DIM}]  Dry run — no changes written.[/{DIM}]")
        return

    try:
        confirmed = Confirm.ask("\n  Confirm write?", default=False)
    except (KeyboardInterrupt, EOFError):
        confirmed = False

    if not confirmed:
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        raise typer.Exit(0)

    _write_note(path, note_name, new_content)
    console.print(f"\n[green]✓[/green] Structure fixed in [bold]{note_name}[/bold]")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


# ── tags ───────────────────────────────────────────────────────────────────

@note_app.command("tags")
def cmd_tags(
    note: Annotated[str, typer.Argument(help="Note name (fuzzy matched)")],
    apply: Annotated[bool, typer.Option("--apply", help="Write tags back to frontmatter")] = False,
) -> None:
    """Propose frontmatter tags for a note. Use --apply to write them."""
    content, path, meta = _resolve_note(note)
    note_name = path.stem

    existing_tags = meta.get("tags", [])
    if isinstance(existing_tags, str):
        existing_tags = existing_tags.split()
    existing_str = json.dumps(existing_tags)

    prompt_text = load_prompt(
        "tags",
        note_content=_note_preview(content, 2000),
        existing_tags=existing_str,
    )

    with console.status(f"[{DIM}]Proposing tags for '{note_name}'…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="note_tags",
                prompt=prompt_text,
                max_tokens=200,
                command="note tags",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    proposed = _parse_json_list(resp.content)
    if not proposed:
        _die(f"AI returned unexpected tags response: {resp.content[:200]}")

    console.print(f"\n  [{INDIGO}]Proposed tags for[/{INDIGO}] [bold]{note_name}[/bold]:\n")
    for tag in proposed:
        marker = "[green]✓[/green]" if tag in existing_tags else "[yellow]+[/yellow]"
        console.print(f"  {marker} {tag}")
    console.print()

    if not apply:
        console.print(f"  [{DIM}]Run with --apply to write tags to frontmatter.[/{DIM}]")
        console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")
        return

    # Apply: update the frontmatter tags field
    new_content = _set_frontmatter_tags(content, proposed)

    try:
        confirmed = Confirm.ask("  Write tags to frontmatter?", default=False)
    except (KeyboardInterrupt, EOFError):
        confirmed = False

    if not confirmed:
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        raise typer.Exit(0)

    _write_note(path, note_name, new_content)
    console.print(f"[green]✓[/green] Tags written to [bold]{note_name}[/bold]")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


def _set_frontmatter_tags(content: str, tags: list[str]) -> str:
    """Return note content with frontmatter tags replaced."""
    # Build new tags block: YAML list format
    tags_yaml = "tags:\n" + "".join(f"  - {t}\n" for t in tags)

    # If frontmatter exists, replace the tags line(s)
    fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not fm_match:
        # No frontmatter — prepend minimal one
        return f"---\n{tags_yaml}---\n\n{content}"

    fm_body = fm_match.group(1)

    # Remove existing tags block (single-line or list)
    fm_body = re.sub(r"^tags:.*?(?=\n[a-z]|\Z)", "", fm_body, flags=re.DOTALL | re.MULTILINE).strip()

    new_fm = f"---\n{fm_body}\n{tags_yaml}---\n"
    return new_fm + content[fm_match.end():]


# ── summarise ──────────────────────────────────────────────────────────────

@note_app.command("autolink")
def cmd_autolink(
    note: Annotated[str, typer.Argument(help="Note name (fuzzy matched)")],
) -> None:
    """Scan a note and add [[wikilinks]] to matching vault notes."""
    content, path, meta = _resolve_note(note)
    note_name = path.stem
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    all_titles = sorted({p.stem for p in iter_notes(vault_path) if p.stem != note_name})
    if not all_titles:
        console.print(f"[{DIM}]  No other notes in vault.[/{DIM}]")
        return

    titles_block = "\n".join(f"- {t}" for t in all_titles[:300])
    prompt_text = load_prompt("note_autolink", note_content=content, vault_titles=titles_block)

    with console.status(f"[{DIM}]Finding link opportunities in '{note_name}'…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="note_autolink",
                prompt=prompt_text,
                max_tokens=3000,
                command="note autolink",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    new_content = resp.content.strip()
    if not new_content or new_content == content.strip():
        console.print(f"  [{DIM}]No new links found in '{note_name}'.[/{DIM}]")
        return

    if not _confirm_write(path, content, new_content, "Added wikilinks"):
        console.print(f"[{DIM}]  Aborted.[/{DIM}]")
        raise typer.Exit(0)

    _write_note(path, note_name, new_content)
    console.print(f"\n[green]✓[/green] Links added to [bold]{note_name}[/bold]")
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


@note_app.command("summarise")
def cmd_summarise(
    note: Annotated[str, typer.Argument(help="Note name (fuzzy matched)")],
) -> None:
    """Print a structured summary of a note. Read-only."""
    content, path, meta = _resolve_note(note)
    note_name = path.stem

    prompt_text = load_prompt(
        "summarise",
        note_title=note_name,
        note_content=_note_preview(content, 3000),
    )

    with console.status(f"[{DIM}]Summarising '{note_name}'…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="note_summarise",
                prompt=prompt_text,
                max_tokens=600,
                command="note summarise",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    console.print(Panel(
        Markdown(resp.content.strip()),
        title=f"[{INDIGO}]{note_name}[/{INDIGO}]",
        border_style=INDIGO,
    ))
    console.print(f"[{DIM}]  {resp.meta_line()}[/{DIM}]\n")
