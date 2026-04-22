"""Tests for commands/project.py."""

from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from obsmind.cli import app
from obsmind.core.ai import AIResponse
from obsmind.core.retrieval import ScoredNote

runner = CliRunner()
VAULT  = Path("/fake/vault")

PROJECT_CONTENT = """\
---
tags:
  - project
status: Active
---
# DeckForge
## Overview
AI-powered flashcard generator.
## Next Steps
- [ ] Build prompt strategy
- [ ] Set up React project
"""

BRIEF = """\
**Status** — Active
**Last active** — 2026-04-21

**Done**
- Proved concept at StudyBuddy hackathon

**In progress**
- Prompt engineering research

**Blocked**
- Nothing identified

**Next steps**
- Build prompt strategy
- Set up React + Node project

**Summary**
DeckForge is an AI flashcard generator in early planning, with concept validated.
"""


def _fake_resp() -> AIResponse:
    return AIResponse(
        content=BRIEF,
        model="claude-sonnet-4-6",
        task="project_status",
        input_tokens=300,
        output_tokens=150,
        cost_usd=0.005,
        elapsed_ms=400,
    )


def _fake_note_path(tmp_path):
    p = tmp_path / "DeckForge.md"
    p.write_text(PROJECT_CONTENT)
    return p


# ── happy path ────────────────────────────────────────────────────────────

def test_project_renders_panel(tmp_path):
    note = _fake_note_path(tmp_path)

    with patch("obsmind.commands.project.load_config", return_value={"daily_notes_folder": "Daily Notes"}), \
         patch("obsmind.commands.project.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.project.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.project.find_daily_notes", return_value=[]), \
         patch("obsmind.commands.project.retrieve", return_value=[]), \
         patch("obsmind.commands.project.ai_core.call", return_value=_fake_resp()):

        result = runner.invoke(app, ["project", "DeckForge"])
        assert result.exit_code == 0
        assert "Done" in result.output
        assert "Next steps" in result.output


def test_project_shows_status_colour(tmp_path):
    note = _fake_note_path(tmp_path)

    with patch("obsmind.commands.project.load_config", return_value={"daily_notes_folder": "Daily Notes"}), \
         patch("obsmind.commands.project.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.project.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.project.find_daily_notes", return_value=[]), \
         patch("obsmind.commands.project.retrieve", return_value=[]), \
         patch("obsmind.commands.project.ai_core.call", return_value=_fake_resp()):

        result = runner.invoke(app, ["project", "DeckForge"])
        assert "Active" in result.output


def test_project_not_found(tmp_path):
    with patch("obsmind.commands.project.load_config", return_value={}), \
         patch("obsmind.commands.project.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.project.find_note_fuzzy", return_value=None):

        result = runner.invoke(app, ["project", "nonexistent"])
        assert result.exit_code == 1
        assert "No note found" in result.output


def test_project_scans_daily_mentions(tmp_path):
    note = _fake_note_path(tmp_path)
    daily_dir = tmp_path / "Daily Notes"
    daily_dir.mkdir()
    yesterday = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    (daily_dir / f"{yesterday}.md").write_text("## Focus Areas\n- Worked on DeckForge prompts\n")

    with patch("obsmind.commands.project.load_config", return_value={"daily_notes_folder": "Daily Notes"}), \
         patch("obsmind.commands.project.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.project.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.project.retrieve", return_value=[]), \
         patch("obsmind.commands.project.ai_core.call", return_value=_fake_resp()) as mock_call:

        runner.invoke(app, ["project", "DeckForge"])
        prompt = mock_call.call_args[1].get("prompt") or mock_call.call_args[0][1]
        assert "DeckForge" in prompt


def test_project_vault_error():
    with patch("obsmind.commands.project.load_config", return_value={}), \
         patch("obsmind.commands.project.resolve_vault_path", side_effect=FileNotFoundError("vault not found")):

        result = runner.invoke(app, ["project", "DeckForge"])
        assert result.exit_code == 1
        assert "vault not found" in result.output


def test_project_accepts_unquoted_name(tmp_path):
    note = _fake_note_path(tmp_path)

    with patch("obsmind.commands.project.load_config", return_value={"daily_notes_folder": "Daily Notes"}), \
         patch("obsmind.commands.project.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.project.find_note_fuzzy", return_value=note) as mock_fuzzy, \
         patch("obsmind.commands.project.find_daily_notes", return_value=[]), \
         patch("obsmind.commands.project.retrieve", return_value=[]), \
         patch("obsmind.commands.project.ai_core.call", return_value=_fake_resp()):

        runner.invoke(app, ["project", "Deck", "Forge"])
        query = mock_fuzzy.call_args[0][1]
        assert query == "Deck Forge"
