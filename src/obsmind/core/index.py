"""Read-only access to the ObsFlow vault index (.obsflow/index.json).

Never modifies index.json — that is ObsFlow's output. Raises helpful errors
if the index is missing or malformed.
"""

import json
from pathlib import Path
from typing import Any

_INDEX_REL = ".obsflow/index.json"

_REQUIRED_KEYS = {"notes", "builtAt"}


class IndexError(Exception):
    pass


def index_path(vault_path: Path) -> Path:
    return vault_path / _INDEX_REL


def load_index(vault_path: Path) -> dict[str, Any]:
    """Load and validate the ObsFlow index.

    Raises IndexError with a fix hint if missing or invalid.
    """
    path = index_path(vault_path)

    if not path.exists():
        raise IndexError(
            f"ObsFlow index not found at {path}.\n"
            "Fix: run 'obs index rebuild' to generate it."
        )

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise IndexError(
            f"ObsFlow index is corrupt ({e}).\n"
            "Fix: run 'obs index rebuild' to regenerate it."
        ) from e

    missing = _REQUIRED_KEYS - set(data.keys())
    if missing:
        raise IndexError(
            f"ObsFlow index is missing keys: {', '.join(missing)}.\n"
            "Fix: run 'obs index rebuild'."
        )

    return data


def get_notes(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the notes dict from an already-loaded index."""
    return index.get("notes", {})


def get_titles(index: dict[str, Any]) -> list[str]:
    """Return all note titles from the index."""
    return [rec.get("title", "") for rec in index.get("notes", {}).values()]


def get_incoming_links(index: dict[str, Any], rel_path: str) -> list[str]:
    """Return relative paths of notes that link to rel_path."""
    rec = index.get("notes", {}).get(rel_path)
    if rec is None:
        return []
    return rec.get("incomingLinks", [])


def stats(index: dict[str, Any]) -> dict[str, Any]:
    """Compute summary statistics from the index."""
    notes = list(index.get("notes", {}).values())
    return {
        "note_count":   len(notes),
        "link_count":   sum(len(r.get("outgoingLinks", [])) for r in notes),
        "tag_count":    len({t for r in notes for t in r.get("tags", [])}),
        "word_count":   sum(r.get("wordCount", 0) for r in notes),
        "built_at":     index.get("builtAt", ""),
        "elapsed_ms":   index.get("elapsed", 0),
    }
