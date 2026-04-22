"""Read-only vault access.

Resolves the vault path (from ~/.obsmindrc, then ~/.obsflowrc), reads notes,
and parses frontmatter. Never writes to vault files directly.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import frontmatter

# ── config paths ───────────────────────────────────────────────────────────

OBSMIND_RC  = Path.home() / ".obsmindrc"
OBSFLOW_RC  = Path.home() / ".obsflowrc"
STATE_DIR   = Path.home() / ".obsmind"
CONFIG_FILE = STATE_DIR / "config.json"


# ── config ─────────────────────────────────────────────────────────────────

_DEFAULT_CONFIG: dict[str, Any] = {
    "vault_path":          "",
    "profile":             "dev",
    "daily_notes_folder":  "Daily Notes",
    "context_notes":       [],
    "priorities_note":     "",
}


def load_config() -> dict[str, Any]:
    """Load ~/.obsmind/config.json, merged with defaults."""
    if CONFIG_FILE.exists():
        try:
            raw = json.loads(CONFIG_FILE.read_text())
            return {**_DEFAULT_CONFIG, **raw}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULT_CONFIG)


def save_config(config: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


def resolve_vault_path(config: dict[str, Any] | None = None) -> Path:
    """Return the vault path, auto-detecting from ObsFlow config if needed.

    Raises FileNotFoundError with a fix hint if nothing resolves.
    """
    cfg = config or load_config()

    if cfg.get("vault_path"):
        p = Path(cfg["vault_path"])
        if p.exists():
            return p

    # Fall back to ObsFlow config
    if OBSFLOW_RC.exists():
        try:
            obsflow = json.loads(OBSFLOW_RC.read_text())
            vp = obsflow.get("vaultPath", "")
            if vp:
                p = Path(vp)
                if p.exists():
                    return p
        except (json.JSONDecodeError, OSError):
            pass

    raise FileNotFoundError(
        "Cannot find vault path.\n"
        "Fix: run 'obsmind config set vault_path /path/to/vault' "
        "or run 'obs init' to configure ObsFlow first."
    )


# ── note reading ────────────────────────────────────────────────────────────

def read_note(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a markdown note. Returns (frontmatter_dict, body_text)."""
    post = frontmatter.load(str(path))
    return dict(post.metadata), post.content


def iter_notes(vault_path: Path) -> list[Path]:
    """Return all .md files in the vault (excluding .obsidian and .obsflow)."""
    return [
        p for p in vault_path.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(vault_path).parts)
    ]


def find_daily_notes(vault_path: Path, folder: str, days: int = 7) -> list[tuple[str, Path]]:
    """Return (date_str, path) for the last `days` daily notes that exist."""
    daily_dir = vault_path / folder
    result = []
    today = datetime.today()
    for i in range(days):
        dt = today - timedelta(days=i)
        date_str = dt.strftime("%Y-%m-%d")
        path = daily_dir / f"{date_str}.md"
        if path.exists():
            result.append((date_str, path))
    return result


def find_project_notes(vault_path: Path) -> list[Path]:
    """Return notes that look like project notes.

    Heuristic: in a 'Projects' folder OR tagged with 'project' in frontmatter.
    """
    projects = []
    for p in iter_notes(vault_path):
        parts = p.relative_to(vault_path).parts
        if any(part.lower() == "projects" for part in parts):
            projects.append(p)
            continue
        try:
            meta, _ = read_note(p)
            tags = meta.get("tags", [])
            if isinstance(tags, list) and "project" in tags:
                projects.append(p)
            elif isinstance(tags, str) and "project" in tags.split():
                projects.append(p)
        except Exception:
            continue
    return projects


def find_note_by_title(vault_path: Path, title: str) -> Path | None:
    """Find a note by exact title (filename without .md extension)."""
    for p in iter_notes(vault_path):
        if p.stem == title:
            return p
    return None


def find_note_fuzzy(vault_path: Path, query: str) -> Path | None:
    """Find a note by fuzzy title match (exact first, then prefix, then substring)."""
    query_lower = query.lower()
    candidates: list[Path] = []
    for p in iter_notes(vault_path):
        stem_lower = p.stem.lower()
        if stem_lower == query_lower:
            return p  # exact match
        if stem_lower.startswith(query_lower) or query_lower in stem_lower:
            candidates.append(p)
    return candidates[0] if len(candidates) == 1 else (candidates[0] if candidates else None)


def get_today_note(vault_path: Path, daily_folder: str) -> Path | None:
    """Return today's daily note path if it exists, else None."""
    today = datetime.today().strftime("%Y-%m-%d")
    path = vault_path / daily_folder / f"{today}.md"
    return path if path.exists() else None


def read_today_note(vault_path: Path, daily_folder: str) -> tuple[str, Path]:
    """Read today's daily note. Raises FileNotFoundError if missing.

    Returns (content, path).
    """
    path = get_today_note(vault_path, daily_folder)
    if path is None:
        today = datetime.today().strftime("%Y-%m-%d")
        raise FileNotFoundError(
            f"No daily note for today ({today}).\n"
            "Fix: run 'obs daily' to create it from the template."
        )
    return path.read_text(), path
