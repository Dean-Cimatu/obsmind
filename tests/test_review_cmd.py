"""Tests for commands/review.py — review and prioritise commands."""

from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from obsmind.cli import app
from obsmind.core.ai import AIResponse

runner = CliRunner()

VAULT_PATH = Path("/fake/vault")


def _fake_resp(content: str, task: str = "review") -> AIResponse:
    return AIResponse(
        content=content,
        model="claude-opus-4-7",
        task=task,
        input_tokens=500,
        output_tokens=300,
        cost_usd=0.03,
        elapsed_ms=800,
    )


def _fake_daily_notes():
    note = VAULT_PATH / "Daily Notes" / "2026-04-21.md"
    return [("2026-04-21", note)]


def _fake_project_paths():
    return [VAULT_PATH / "Projects" / "Project Alpha.md"]


# ── review ────────────────────────────────────────────────────────────────

def test_review_streams_output():
    with patch("obsmind.commands.review.load_config", return_value={}), \
         patch("obsmind.commands.review.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.review.find_daily_notes", return_value=_fake_daily_notes()), \
         patch("obsmind.commands.review.find_project_notes", return_value=[]), \
         patch("obsmind.commands.review.read_note", return_value=({}, "## Tasks\n- [x] Done")), \
         patch("obsmind.commands.review.load_context", return_value="ctx"), \
         patch("obsmind.commands.review.ai_core.stream", return_value=iter(["**What got done**\n", "- Shipped feature\n"])):

        result = runner.invoke(app, ["review"])
        assert "What got done" in result.output
        assert result.exit_code == 0


def test_review_no_daily_notes():
    with patch("obsmind.commands.review.load_config", return_value={}), \
         patch("obsmind.commands.review.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.review.find_daily_notes", return_value=[]), \
         patch("obsmind.commands.review.find_project_notes", return_value=[]):

        result = runner.invoke(app, ["review"])
        assert result.exit_code == 1
        assert "No daily notes" in result.output


def test_review_vault_error():
    with patch("obsmind.commands.review.load_config", return_value={}), \
         patch("obsmind.commands.review.resolve_vault_path", side_effect=FileNotFoundError("vault not found")):

        result = runner.invoke(app, ["review"])
        assert result.exit_code == 1
        assert "vault not found" in result.output


def test_review_days_option():
    with patch("obsmind.commands.review.load_config", return_value={}), \
         patch("obsmind.commands.review.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.review.find_daily_notes", return_value=_fake_daily_notes()) as mock_find, \
         patch("obsmind.commands.review.find_project_notes", return_value=[]), \
         patch("obsmind.commands.review.read_note", return_value=({}, "content")), \
         patch("obsmind.commands.review.load_context", return_value="ctx"), \
         patch("obsmind.commands.review.ai_core.stream", return_value=iter(["output"])):

        runner.invoke(app, ["review", "--days", "14"])
        call_args = mock_find.call_args
        assert call_args[1].get("days") == 14 or call_args[0][2] == 14


# ── prioritise ────────────────────────────────────────────────────────────

def test_prioritise_shows_panel():
    with patch("obsmind.commands.review.load_config", return_value={"daily_notes_folder": "Daily Notes"}), \
         patch("obsmind.commands.review.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.review.find_daily_notes", return_value=_fake_daily_notes()), \
         patch("obsmind.commands.review.find_project_notes", return_value=[]), \
         patch("obsmind.commands.review.read_note", return_value=({}, "## Tasks\n- [ ] Write tests\n- [ ] Deploy")), \
         patch("obsmind.commands.review.load_context", return_value="ctx"), \
         patch("obsmind.commands.review.ai_core.call", return_value=_fake_resp("1. [Projects] Write tests\n2. [Projects] Deploy", "prioritise")):

        result = runner.invoke(app, ["prioritise"])
        assert "Write tests" in result.output
        assert result.exit_code == 0


def test_prioritise_no_tasks():
    with patch("obsmind.commands.review.load_config", return_value={}), \
         patch("obsmind.commands.review.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.review.find_daily_notes", return_value=[]), \
         patch("obsmind.commands.review.find_project_notes", return_value=[]), \
         patch("obsmind.commands.review.read_note", return_value=({}, "no tasks here")):

        result = runner.invoke(app, ["prioritise"])
        assert "No open tasks" in result.output
        assert result.exit_code == 0


def test_prioritise_api_error():
    with patch("obsmind.commands.review.load_config", return_value={}), \
         patch("obsmind.commands.review.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.review.find_daily_notes", return_value=_fake_daily_notes()), \
         patch("obsmind.commands.review.find_project_notes", return_value=[]), \
         patch("obsmind.commands.review.read_note", return_value=({}, "- [ ] A task")), \
         patch("obsmind.commands.review.load_context", return_value="ctx"), \
         patch("obsmind.commands.review.ai_core.call", side_effect=EnvironmentError("API key missing")):

        result = runner.invoke(app, ["prioritise"])
        assert result.exit_code == 1
        assert "API key" in result.output
