"""Tests for commands/generate.py."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from obsmind.cli import app
from obsmind.core.ai import AIResponse
from obsmind.core.retrieval import ScoredNote

runner = CliRunner()

VAULT_PATH = Path("/fake/vault")

GENERATED_NOTE = """\
---
tags:
  - project
  - planning
created: 2026-04-22
status: draft
---

# New Project

## Overview
This is a new project note.

## Goals
- Ship the feature

## Next Steps
- [ ] Start implementation
"""


def _fake_resp(content: str = GENERATED_NOTE) -> AIResponse:
    return AIResponse(
        content=content,
        model="claude-opus-4-7",
        task="generate",
        input_tokens=300,
        output_tokens=200,
        cost_usd=0.02,
        elapsed_ms=600,
    )


def _patch_base(note_exists: bool = False):
    target = VAULT_PATH / "New Project.md"
    return [
        patch("obsmind.commands.generate.load_config", return_value={}),
        patch("obsmind.commands.generate.resolve_vault_path", return_value=VAULT_PATH),
        patch("pathlib.Path.exists", return_value=note_exists),
        patch("obsmind.commands.generate.retrieve", return_value=[]),
        patch("obsmind.commands.generate.load_context", return_value="ctx"),
    ]


# ── generate ──────────────────────────────────────────────────────────────

def test_generate_dry_run_shows_preview(tmp_path):
    with patch("obsmind.commands.generate.load_config", return_value={}), \
         patch("obsmind.commands.generate.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.generate.retrieve", return_value=[]), \
         patch("obsmind.commands.generate.load_context", return_value="ctx"), \
         patch("obsmind.commands.generate.ai_core.call", return_value=_fake_resp()):

        result = runner.invoke(app, ["generate", "New Project", "--instruction", "project planning note", "--dry-run"])
        assert "Dry run" in result.output
        assert result.exit_code == 0


def test_generate_aborts_on_no(tmp_path):
    target = tmp_path / "New Project.md"

    with patch("obsmind.commands.generate.load_config", return_value={}), \
         patch("obsmind.commands.generate.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.generate.retrieve", return_value=[]), \
         patch("obsmind.commands.generate.load_context", return_value="ctx"), \
         patch("obsmind.commands.generate.ai_core.call", return_value=_fake_resp()), \
         patch("obsmind.commands.generate.Confirm.ask", return_value=False):

        result = runner.invoke(app, ["generate", "New Project", "--instruction", "planning note"])
        assert "Aborted" in result.output
        assert result.exit_code == 0


def test_generate_creates_note(tmp_path):
    with patch("obsmind.commands.generate.load_config", return_value={}), \
         patch("obsmind.commands.generate.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.generate.retrieve", return_value=[]), \
         patch("obsmind.commands.generate.load_context", return_value="ctx"), \
         patch("obsmind.commands.generate.ai_core.call", return_value=_fake_resp()), \
         patch("obsmind.commands.generate.Confirm.ask", return_value=True), \
         patch("obsmind.commands.generate.create_note") as mock_create:

        result = runner.invoke(app, ["generate", "New Project", "--instruction", "planning note"])
        assert mock_create.called
        assert result.exit_code == 0
        assert "Created" in result.output


def test_generate_fails_if_note_exists(tmp_path):
    existing = tmp_path / "Existing Note.md"
    existing.write_text("already here")

    with patch("obsmind.commands.generate.load_config", return_value={}), \
         patch("obsmind.commands.generate.resolve_vault_path", return_value=tmp_path):

        result = runner.invoke(app, ["generate", "Existing Note", "--instruction", "something"])
        assert result.exit_code == 1
        assert "already exists" in result.output


def test_generate_with_folder(tmp_path):
    with patch("obsmind.commands.generate.load_config", return_value={}), \
         patch("obsmind.commands.generate.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.generate.retrieve", return_value=[]), \
         patch("obsmind.commands.generate.load_context", return_value="ctx"), \
         patch("obsmind.commands.generate.ai_core.call", return_value=_fake_resp()), \
         patch("obsmind.commands.generate.Confirm.ask", return_value=True), \
         patch("obsmind.commands.generate.create_note") as mock_create:

        result = runner.invoke(app, ["generate", "My Note", "--instruction", "content", "--folder", "Projects"])
        assert mock_create.called
        call_kwargs = mock_create.call_args
        assert "Projects" in str(call_kwargs)


def test_generate_vault_error():
    with patch("obsmind.commands.generate.load_config", return_value={}), \
         patch("obsmind.commands.generate.resolve_vault_path", side_effect=FileNotFoundError("vault not found")):

        result = runner.invoke(app, ["generate", "Note", "--instruction", "something"])
        assert result.exit_code == 1
        assert "vault not found" in result.output


def test_generate_uses_related_notes(tmp_path):
    related = [ScoredNote(path=tmp_path / "Related.md", title="Related", score=2.0, matched_terms=["project"])]

    with patch("obsmind.commands.generate.load_config", return_value={}), \
         patch("obsmind.commands.generate.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.generate.retrieve", return_value=related), \
         patch("obsmind.commands.generate.load_context", return_value="ctx"), \
         patch("obsmind.commands.generate.ai_core.call", return_value=_fake_resp()) as mock_call, \
         patch("obsmind.commands.generate.Confirm.ask", return_value=False):

        runner.invoke(app, ["generate", "New Note", "--instruction", "project planning"])
        prompt_arg = mock_call.call_args[1].get("prompt") or mock_call.call_args[0][1]
        assert "Related" in prompt_arg
