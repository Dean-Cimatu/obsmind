"""System prompt context builder.

Reads active project notes, recent daily notes, and priorities, then
assembles a context block that tells Claude who the user is and what they
are working on. Cached to ~/.obsmind/context.md.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from .vault import (
    load_config,
    resolve_vault_path,
    read_note,
    find_daily_notes,
    find_project_notes,
    find_note_by_title,
)
from .profiles import get_profile

CONTEXT_FILE = Path.home() / ".obsmind" / "context.md"

_MAX_PROJECT_CHARS = 800
_MAX_DAILY_CHARS   = 600
_MAX_PRIORITY_CHARS = 1200


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit("\n", 1)[0] + "\n…"


def build_context(config: dict[str, Any] | None = None) -> str:
    """Read vault and assemble the full context markdown block."""
    cfg = config or load_config()
    vault_path = resolve_vault_path(cfg)
    daily_folder = cfg.get("daily_notes_folder", "Daily Notes")

    sections: list[str] = [
        f"# ObsMind Context\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n",
    ]

    # ── active projects ───────────────────────────────────────────────────
    project_paths = find_project_notes(vault_path)
    extra_titles  = cfg.get("context_notes", [])
    for title in extra_titles:
        p = find_note_by_title(vault_path, title)
        if p and p not in project_paths:
            project_paths.append(p)

    if project_paths:
        sections.append("## Active Projects\n")
        for p in project_paths[:10]:
            try:
                meta, body = read_note(p)
                title = meta.get("title") or p.stem
                preview = _truncate(body.strip(), _MAX_PROJECT_CHARS)
                sections.append(f"### [[{title}]]\n{preview}\n")
            except Exception:
                sections.append(f"### [[{p.stem}]]\n_(could not read note)_\n")

    # ── recent daily notes ────────────────────────────────────────────────
    recent = find_daily_notes(vault_path, daily_folder, days=7)
    if recent:
        sections.append("## Recent Daily Notes\n")
        for date_str, path in recent:
            try:
                _, body = read_note(path)
                preview = _truncate(body.strip(), _MAX_DAILY_CHARS)
                sections.append(f"### {date_str}\n{preview}\n")
            except Exception:
                sections.append(f"### {date_str}\n_(could not read note)_\n")

    # ── priorities ────────────────────────────────────────────────────────
    priorities_title = cfg.get("priorities_note", "")
    if priorities_title:
        p = find_note_by_title(vault_path, priorities_title)
        if p:
            try:
                _, body = read_note(p)
                sections.append(
                    "## Priorities\n"
                    + _truncate(body.strip(), _MAX_PRIORITY_CHARS)
                    + "\n"
                )
            except Exception:
                pass

    # ── profile addition ──────────────────────────────────────────────────
    profile_name = cfg.get("profile", "dev")
    try:
        profile = get_profile(profile_name)
        addition = profile.system_prompt_addition()
        if addition:
            sections.append(f"## Profile ({profile_name})\n{addition}\n")
    except ValueError:
        pass

    return "\n".join(sections)


def update_context(config: dict[str, Any] | None = None) -> Path:
    """Rebuild and write the context cache. Returns the cache path."""
    content = build_context(config)
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(content)
    return CONTEXT_FILE


def load_context() -> str | None:
    """Return the cached context, or None if not yet generated."""
    if CONTEXT_FILE.exists():
        return CONTEXT_FILE.read_text()
    return None


def system_prompt(config: dict[str, Any] | None = None) -> str:
    """Assemble the full system prompt for an AI call.

    Uses cached context if available; callers should run update_context()
    periodically to keep it fresh.
    """
    cfg = config or load_config()
    profile_name = cfg.get("profile", "dev")

    base = (
        "You are ObsMind, an AI assistant deeply integrated with the user's "
        "Obsidian vault. You have read-only knowledge of their notes, projects, "
        "and recent context. When you reference a note, use [[wikilink]] syntax. "
        "Be concise and precise. Never invent note content — cite only what you "
        "know from the context provided."
    )

    try:
        profile = get_profile(profile_name)
        base = base + "\n\n" + profile.system_prompt_addition()
    except ValueError:
        pass

    ctx = load_context()
    if ctx:
        base = base + "\n\n" + ctx

    return base
