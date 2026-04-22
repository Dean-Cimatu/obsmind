"""Commands: obsmind ask + obsmind find."""

import json
import re
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ..core import ai as ai_core
from ..core.context import load_context
from ..core.prompts import load as load_prompt
from ..core.retrieval import retrieve, format_for_prompt
from ..core.vault import load_config, resolve_vault_path, iter_notes, read_note

console = Console()

INDIGO = "bright_blue"
DIM    = "dim"

# Auto-escalate to Opus when question contains these analytical patterns
_OPUS_PATTERNS = re.compile(
    r"\b(compare|contrast|analys[ei]|analyze|what patterns|across|correlat|synthesise|synthesize|overview of all)\b",
    re.IGNORECASE,
)
_OPUS_SOURCE_THRESHOLD = 9


def _die(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(1)


# ── ask ────────────────────────────────────────────────────────────────────

def ask_command(
    question: str,
    limit: int,
    opus: bool,
) -> None:
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    with console.status(f"[{DIM}]Searching vault…[/{DIM}]"):
        results = retrieve(vault_path, question, limit=limit)

    if not results:
        console.print(f"[yellow]⚠[/yellow]  No relevant notes found for '{question}'.")
        return

    retrieved_block = format_for_prompt(results, max_chars_each=800)
    user_ctx = load_context() or "(no context cached — run obsmind context update)"

    # Auto-escalate to Opus for analytical questions or large source sets
    auto_opus = opus or len(results) >= _OPUS_SOURCE_THRESHOLD or bool(_OPUS_PATTERNS.search(question))
    task = "ask_opus" if auto_opus else "ask"

    prompt_text = load_prompt(
        "ask",
        user_context=user_ctx[:600],
        retrieved_notes=retrieved_block,
        question=question,
    )

    with console.status(f"[{DIM}]Answering with {len(results)} source(s)…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task=task,
                prompt=prompt_text,
                max_tokens=1500,
                command="ask",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    tier_label = "[yellow](opus)[/yellow]" if auto_opus and not opus else ""
    console.print(Panel(
        Markdown(resp.content.strip()),
        title=f"[{INDIGO}]ObsMind Answer[/{INDIGO}] {tier_label}",
        border_style=INDIGO,
    ))
    console.print(f"[{DIM}]  {len(results)} sources  {resp.meta_line()}[/{DIM}]\n")


# ── find ───────────────────────────────────────────────────────────────────

def find_command(
    query: str,
    limit: int,
) -> None:
    cfg = load_config()
    try:
        vault_path = resolve_vault_path(cfg)
    except FileNotFoundError as e:
        _die(str(e))

    with console.status(f"[{DIM}]Scanning vault…[/{DIM}]"):
        # Gather candidates from keyword retrieval with a wide net
        candidates = retrieve(vault_path, query, limit=max(limit * 4, 20))

    if not candidates:
        console.print(f"[yellow]⚠[/yellow]  No candidates found for '{query}'.")
        return

    # Build candidate block for Claude to rank
    candidates_block = "\n".join(
        f"- {c.title} (terms: {', '.join(c.matched_terms)})" for c in candidates
    )

    prompt_text = load_prompt(
        "find",
        query=query,
        candidates=candidates_block,
    )

    with console.status(f"[{DIM}]Ranking {len(candidates)} candidates…[/{DIM}]"):
        try:
            resp = ai_core.call(
                task="find",
                prompt=prompt_text,
                max_tokens=800,
                command="find",
            )
        except (EnvironmentError, ValueError) as e:
            _die(str(e))

    ranked = _parse_ranked(resp.content)
    if not ranked:
        # Fall back to raw keyword order
        ranked = [{"title": c.title, "score": round(c.score / max(c.score, 1), 2), "reason": "(keyword match)"} for c in candidates[:limit]]

    table = Table(show_header=True, header_style="bold")
    table.add_column("Score", style="yellow", width=6)
    table.add_column("Note", style="bold")
    table.add_column("Reason", style=DIM)

    for item in ranked[:limit]:
        score  = item.get("score", 0.0)
        title  = item.get("title", "")
        reason = item.get("reason", "")
        table.add_row(f"{score:.2f}", title, reason)

    console.print(f"\n  [{INDIGO}]Find:[/{INDIGO}] [bold]{query}[/bold]\n")
    console.print(table)
    console.print(f"\n[{DIM}]  {resp.meta_line()}[/{DIM}]\n")


def _parse_ranked(text: str) -> list[dict]:
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        result = json.loads(match.group())
        return [r for r in result if isinstance(r, dict) and "title" in r]
    except json.JSONDecodeError:
        return []


# ── Typer commands registered in cli.py ───────────────────────────────────

def register(app: typer.Typer) -> None:
    """Register ask and find as top-level commands on the given app."""

    @app.command("ask", context_settings={"allow_extra_args": False, "ignore_unknown_options": False})
    def cmd_ask(
        words: Annotated[list[str], typer.Argument(help="Question to ask your vault")],
        limit: Annotated[int, typer.Option("--limit", "-l", help="Max sources to retrieve")] = 5,
        opus: Annotated[bool, typer.Option("--opus", help="Force Opus for the answer")] = False,
    ) -> None:
        """Ask a question — Claude answers using your vault notes as sources."""
        ask_command(" ".join(words), limit=limit, opus=opus)

    @app.command("find")
    def cmd_find(
        words: Annotated[list[str], typer.Argument(help="What to search for")],
        limit: Annotated[int, typer.Option("--limit", "-l", help="Max results")] = 10,
    ) -> None:
        """Find and rank notes relevant to a query."""
        find_command(" ".join(words), limit=limit)
