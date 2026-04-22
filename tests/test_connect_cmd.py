"""Tests for commands/connect.py."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from obsmind.cli import app
from obsmind.core.ai import AIResponse
from obsmind.core.retrieval import ScoredNote

runner = CliRunner()
VAULT  = Path("/fake/vault")

NOTE_CONTENT = """\
---
tags: [project, ai]
---
# DeckForge
AI-powered flashcard generator using Claude API.
## Overview
Creates Q&A pairs from notes automatically.
"""

CONNECTIONS_JSON = """[
  {"title": "StudySync", "reason": "Both are EdTech projects targeting student productivity", "suggested_text": "flashcard generator"},
  {"title": "Claude API Notes", "reason": "DeckForge is built on Claude API — direct dependency", "suggested_text": "Claude API"}
]"""


def _fake_resp(content: str = CONNECTIONS_JSON) -> AIResponse:
    return AIResponse(
        content=content,
        model="claude-sonnet-4-6",
        task="connect",
        input_tokens=400,
        output_tokens=150,
        cost_usd=0.007,
        elapsed_ms=500,
    )


def _fake_candidates():
    return [
        ScoredNote(path=VAULT / "StudySync.md",        title="StudySync",        score=3.0, matched_terms=["study"]),
        ScoredNote(path=VAULT / "Claude API Notes.md", title="Claude API Notes", score=2.0, matched_terms=["claude"]),
        ScoredNote(path=VAULT / "AutoKart.md",         title="AutoKart",         score=1.0, matched_terms=["project"]),
    ]


# ── happy path ────────────────────────────────────────────────────────────

def test_connect_shows_table(tmp_path):
    note = tmp_path / "DeckForge.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.connect.load_config", return_value={}), \
         patch("obsmind.commands.connect.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.connect.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.connect.retrieve", return_value=_fake_candidates()), \
         patch("obsmind.commands.connect.read_note", return_value=({"tags": ["project"]}, NOTE_CONTENT)), \
         patch("obsmind.commands.connect.ai_core.call", return_value=_fake_resp()):

        result = runner.invoke(app, ["connect", "DeckForge"])
        assert result.exit_code == 0
        assert "StudySync" in result.output
        assert "Claude API Notes" in result.output
        assert "EdTech" in result.output


def test_connect_no_candidates(tmp_path):
    note = tmp_path / "DeckForge.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.connect.load_config", return_value={}), \
         patch("obsmind.commands.connect.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.connect.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.connect.retrieve", return_value=[]), \
         patch("obsmind.commands.connect.read_note", return_value=({}, NOTE_CONTENT)):

        result = runner.invoke(app, ["connect", "DeckForge"])
        assert "No candidates" in result.output
        assert result.exit_code == 0


def test_connect_no_connections_found(tmp_path):
    note = tmp_path / "DeckForge.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.connect.load_config", return_value={}), \
         patch("obsmind.commands.connect.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.connect.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.connect.retrieve", return_value=_fake_candidates()), \
         patch("obsmind.commands.connect.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.connect.ai_core.call", return_value=_fake_resp("[]")):

        result = runner.invoke(app, ["connect", "DeckForge"])
        assert "No meaningful connections" in result.output


def test_connect_note_not_found(tmp_path):
    with patch("obsmind.commands.connect.load_config", return_value={}), \
         patch("obsmind.commands.connect.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.connect.find_note_fuzzy", return_value=None):

        result = runner.invoke(app, ["connect", "nonexistent"])
        assert result.exit_code == 1
        assert "No note found" in result.output


def test_connect_excludes_existing_links(tmp_path):
    note = tmp_path / "DeckForge.md"
    # Already links to StudySync
    note.write_text(NOTE_CONTENT + "\n[[StudySync]] is a related project.\n")

    with patch("obsmind.commands.connect.load_config", return_value={}), \
         patch("obsmind.commands.connect.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.connect.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.connect.retrieve", return_value=_fake_candidates()), \
         patch("obsmind.commands.connect.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.connect.ai_core.call", return_value=_fake_resp()) as mock_call:

        runner.invoke(app, ["connect", "DeckForge"])
        prompt = mock_call.call_args[1].get("prompt") or mock_call.call_args[0][1]
        assert "studysync" in prompt.lower()  # should be in the excluded list


def test_connect_apply_aborts_on_no(tmp_path):
    note = tmp_path / "DeckForge.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.connect.load_config", return_value={}), \
         patch("obsmind.commands.connect.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.connect.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.connect.retrieve", return_value=_fake_candidates()), \
         patch("obsmind.commands.connect.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.connect.ai_core.call", return_value=_fake_resp()), \
         patch("obsmind.commands.connect.Confirm.ask", return_value=False):

        result = runner.invoke(app, ["connect", "DeckForge", "--apply"])
        assert result.exit_code == 0


def test_connect_accepts_unquoted_name(tmp_path):
    note = tmp_path / "FS Cone Detection.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.connect.load_config", return_value={}), \
         patch("obsmind.commands.connect.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.connect.find_note_fuzzy", return_value=note) as mock_fuzzy, \
         patch("obsmind.commands.connect.retrieve", return_value=[]), \
         patch("obsmind.commands.connect.read_note", return_value=({}, NOTE_CONTENT)):

        runner.invoke(app, ["connect", "FS", "Cone", "Detection"])
        assert mock_fuzzy.call_args[0][1] == "FS Cone Detection"
