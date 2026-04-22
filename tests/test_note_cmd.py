"""Tests for commands/note.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from obsmind.cli import app
from obsmind.core.ai import AIResponse

runner = CliRunner()

VAULT_PATH = Path("/fake/vault")
NOTE_PATH  = VAULT_PATH / "My Project.md"
NOTE_CONTENT = """---
tags:
  - project
---

## Overview
This is the overview section.

## Tasks
- [ ] Write tests
- [ ] Deploy

## Notes
Some notes here.
"""


def _fake_resp(content: str, task: str = "note_edit") -> AIResponse:
    return AIResponse(
        content=content,
        model="claude-haiku-4-5-20251001",
        task=task,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0001,
        elapsed_ms=200,
    )


def _patch_vault(note_content: str = NOTE_CONTENT):
    return [
        patch("obsmind.commands.note.load_config", return_value={"vault_path": str(VAULT_PATH), "daily_notes_folder": "Daily Notes"}),
        patch("obsmind.commands.note.resolve_vault_path", return_value=VAULT_PATH),
        patch("obsmind.commands.note.find_note_fuzzy", return_value=NOTE_PATH),
        patch("obsmind.commands.note.read_note", return_value=({"tags": ["project"]}, note_content)),
        patch.object(NOTE_PATH, "read_text", return_value=note_content, create=True),
        patch("pathlib.Path.read_text", return_value=note_content),
    ]


# ── edit ──────────────────────────────────────────────────────────────────

def test_edit_aborts_on_no(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({"tags": ["project"]}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp("Updated overview content")), \
         patch("obsmind.commands.note.load_context", return_value="ctx"), \
         patch("obsmind.commands.note.Confirm.ask", return_value=False):

        result = runner.invoke(app, ["note", "edit", "My Project", "--section", "Overview", "--instruction", "Improve it"])
        assert result.exit_code == 0
        assert "Aborted" in result.output


def test_edit_section_not_found(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({"tags": []}, NOTE_CONTENT)):

        result = runner.invoke(app, ["note", "edit", "My Project", "--section", "Nonexistent", "--instruction", "fix"])
        assert result.exit_code == 1
        assert "not found" in result.output


def test_edit_writes_on_confirm(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({"tags": []}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp("New overview content")), \
         patch("obsmind.commands.note.load_context", return_value="ctx"), \
         patch("obsmind.commands.note.Confirm.ask", return_value=True), \
         patch("obsmind.commands.note.rewrite_note") as mock_write:

        result = runner.invoke(app, ["note", "edit", "My Project", "--section", "Overview", "--instruction", "improve"])
        assert mock_write.called
        assert result.exit_code == 0


# ── extend ────────────────────────────────────────────────────────────────

def test_extend_aborts_on_no(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    extend_resp = '{"after_section": "Notes", "content": "New section body"}'
    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp(extend_resp)), \
         patch("obsmind.commands.note.load_context", return_value="ctx"), \
         patch("obsmind.commands.note.Confirm.ask", return_value=False):

        result = runner.invoke(app, ["note", "extend", "My Project", "--section", "References"])
        assert "Aborted" in result.output
        assert result.exit_code == 0


def test_extend_writes_new_section(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    extend_resp = '{"after_section": "Notes", "content": "Reference content here"}'
    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp(extend_resp)), \
         patch("obsmind.commands.note.load_context", return_value="ctx"), \
         patch("obsmind.commands.note.Confirm.ask", return_value=True), \
         patch("obsmind.commands.note.rewrite_note") as mock_write:

        result = runner.invoke(app, ["note", "extend", "My Project", "--section", "References"])
        assert mock_write.called
        assert result.exit_code == 0


# ── enhance ───────────────────────────────────────────────────────────────

def test_enhance_aborts_on_no(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp("Enhanced note content")), \
         patch("obsmind.commands.note.load_context", return_value="ctx"), \
         patch("obsmind.commands.note.Confirm.ask", return_value=False):

        result = runner.invoke(app, ["note", "enhance", "My Project"])
        assert "Aborted" in result.output


# ── rewrite ───────────────────────────────────────────────────────────────

def test_rewrite_requires_section_or_full(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({}, NOTE_CONTENT)):

        result = runner.invoke(app, ["note", "rewrite", "My Project", "--instruction", "improve"])
        assert result.exit_code == 1
        assert "--section" in result.output or "--full" in result.output


def test_rewrite_full_uses_opus_task(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.load_context", return_value="ctx"), \
         patch("obsmind.commands.note.Confirm.ask", return_value=False), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp("Rewritten note", "note_rewrite_full")) as mock_call:

        runner.invoke(app, ["note", "rewrite", "My Project", "--full", "--instruction", "rewrite completely"])
        call_kwargs = mock_call.call_args
        assert call_kwargs[1]["task"] == "note_rewrite_full" or call_kwargs[0][0] == "note_rewrite_full"


# ── fix ───────────────────────────────────────────────────────────────────

def test_fix_dry_run(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)
    fixed = NOTE_CONTENT.replace("## Overview", "## Overview\n")  # minor change

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp(fixed)):

        result = runner.invoke(app, ["note", "fix", "My Project", "--dry-run"])
        assert "Dry run" in result.output
        assert result.exit_code == 0


def test_fix_no_changes(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp(NOTE_CONTENT.strip())):

        result = runner.invoke(app, ["note", "fix", "My Project"])
        assert "No structural issues" in result.output


# ── tags ──────────────────────────────────────────────────────────────────

def test_tags_shows_proposals(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({"tags": ["project"]}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp('["project", "planning", "tasks"]')):

        result = runner.invoke(app, ["note", "tags", "My Project"])
        assert "project" in result.output
        assert "planning" in result.output
        assert result.exit_code == 0


def test_tags_apply_writes(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({"tags": ["project"]}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp('["project", "planning"]')), \
         patch("obsmind.commands.note.Confirm.ask", return_value=True), \
         patch("obsmind.commands.note.rewrite_note") as mock_write:

        result = runner.invoke(app, ["note", "tags", "My Project", "--apply"])
        assert mock_write.called
        assert result.exit_code == 0


# ── summarise ─────────────────────────────────────────────────────────────

def test_summarise_shows_panel(tmp_path):
    note = tmp_path / "My Project.md"
    note.write_text(NOTE_CONTENT)

    with patch("obsmind.commands.note.load_config", return_value={}), \
         patch("obsmind.commands.note.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.note.find_note_fuzzy", return_value=note), \
         patch("obsmind.commands.note.read_note", return_value=({}, NOTE_CONTENT)), \
         patch("obsmind.commands.note.ai_core.call", return_value=_fake_resp("**What this note is about** — project overview.")):

        result = runner.invoke(app, ["note", "summarise", "My Project"])
        assert "What this note is about" in result.output
        assert result.exit_code == 0
