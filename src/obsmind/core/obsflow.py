"""Subprocess bridge to the obs CLI.

ObsMind never writes to the vault directly. Every write goes through obs so
ObsFlow's trash/undo system covers both tools.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any


class ObsFlowError(Exception):
    pass


class ObsFlowNotFoundError(ObsFlowError):
    pass


# ── availability check ─────────────────────────────────────────────────────

def check_available() -> str:
    """Return the path to the obs binary, or raise ObsFlowNotFoundError."""
    path = shutil.which("obs")
    if path is None:
        raise ObsFlowNotFoundError(
            "obs CLI not found in PATH.\n"
            "Fix: install ObsFlow with 'npm install -g obsflow', "
            "then verify with 'which obs'."
        )
    return path


def is_available() -> bool:
    try:
        check_available()
        return True
    except ObsFlowNotFoundError:
        return False


# ── runner ─────────────────────────────────────────────────────────────────

def _run(args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess:
    """Run obs with the given arguments. Raises ObsFlowError on non-zero exit."""
    check_available()
    try:
        result = subprocess.run(
            ["obs", *args],
            capture_output=True,
            text=True,
            input=input_text,
        )
    except FileNotFoundError:
        raise ObsFlowNotFoundError(
            "obs CLI disappeared from PATH.\n"
            "Fix: run 'npm install -g obsflow'."
        )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise ObsFlowError(
            f"obs {' '.join(args)} failed (exit {result.returncode}):\n{stderr}"
        )
    return result


# ── read operations ────────────────────────────────────────────────────────

def version() -> str:
    """Return the installed obs version string."""
    result = _run(["--version"])
    return result.stdout.strip()


def index_rebuild() -> str:
    """Trigger a full vault index rebuild. Returns obs stdout."""
    result = _run(["index", "rebuild"])
    return result.stdout.strip()


def index_stats() -> str:
    """Return raw obs index stats output."""
    result = _run(["index", "stats"])
    return result.stdout.strip()


# ── write operations ───────────────────────────────────────────────────────

def append_section(section: str, text: str) -> str:
    """Append a bullet to a section in today's daily note.

    Equivalent to: obs append <section> "<text>"
    """
    result = _run(["append", section, text, "--quiet"])
    return result.stdout.strip()


def append_to_note(note: str, text: str) -> str:
    """Fuzzy-match a note and append text to it.

    Equivalent to: obs append-to <note> "<text>"
    """
    result = _run(["append-to", note, text, "--quiet"])
    return result.stdout.strip()


def capture(text: str) -> str:
    """Route a capture through the ObsFlow classifier.

    Equivalent to: obs "<text>"
    """
    result = _run([text, "--quiet"])
    return result.stdout.strip()


def todo_capture(text: str) -> str:
    """Add a task to today's Tasks table.

    Equivalent to: obs todo "<text>"
    """
    result = _run(["todo", text, "--quiet"])
    return result.stdout.strip()


_TASKS_SECTION_NAMES = {"tasks", "task"}


def daily_add(section: str, text: str) -> str:
    """Write to today's daily note via the appropriate obs command.

    Routes Tasks-section writes to 'obs todo' (formats as table row).
    All other sections go to 'obs append <section> <text>'.
    This is the canonical write path — never write vault files directly.
    """
    if section.lower() in _TASKS_SECTION_NAMES:
        return todo_capture(text)
    return append_section(section, text)
