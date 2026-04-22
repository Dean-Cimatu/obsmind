"""Tests for commands/standup.py."""

from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from obsmind.cli import app
from obsmind.core.ai import AIResponse

runner = CliRunner()

VAULT_PATH   = Path("/fake/vault")
DAILY_FOLDER = "Daily Notes"

YESTERDAY = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

DAILY_CONTENT = """\
## Focus Areas
- Worked on DeckForge prompt engineering

## Tasks
- [x] Write unit tests
- [ ] Deploy to staging
- [ ] Review PR from team

## Learning Log
Read about spaced repetition algorithms.
"""

STANDUP_OUTPUT = """\
**Done**
- Worked on DeckForge prompt engineering
- Wrote unit tests

**Today**
- Deploy to staging
- Review PR from team

**Blockers**
- None
"""


def _fake_resp(content: str = STANDUP_OUTPUT) -> AIResponse:
    return AIResponse(
        content=content,
        model="claude-haiku-4-5-20251001",
        task="standup",
        input_tokens=150,
        output_tokens=80,
        cost_usd=0.0002,
        elapsed_ms=300,
    )


# ── happy path ────────────────────────────────────────────────────────────

def test_standup_renders_panel(tmp_path):
    daily_dir = tmp_path / DAILY_FOLDER
    daily_dir.mkdir()
    (daily_dir / f"{YESTERDAY}.md").write_text(DAILY_CONTENT)

    with patch("obsmind.commands.standup.load_config", return_value={"daily_notes_folder": DAILY_FOLDER}), \
         patch("obsmind.commands.standup.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.standup.find_project_notes", return_value=[]), \
         patch("obsmind.commands.standup.load_context", return_value="ctx"), \
         patch("obsmind.commands.standup.ai_core.call", return_value=_fake_resp()):

        result = runner.invoke(app, ["standup"])
        assert result.exit_code == 0
        assert "Done" in result.output
        assert "Today" in result.output
        assert "Blockers" in result.output


def test_standup_copy_flag(tmp_path):
    daily_dir = tmp_path / DAILY_FOLDER
    daily_dir.mkdir()
    (daily_dir / f"{YESTERDAY}.md").write_text(DAILY_CONTENT)

    with patch("obsmind.commands.standup.load_config", return_value={"daily_notes_folder": DAILY_FOLDER}), \
         patch("obsmind.commands.standup.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.standup.find_project_notes", return_value=[]), \
         patch("obsmind.commands.standup.load_context", return_value="ctx"), \
         patch("obsmind.commands.standup.ai_core.call", return_value=_fake_resp()), \
         patch("obsmind.commands.standup._copy_to_clipboard") as mock_copy:

        result = runner.invoke(app, ["standup", "--copy"])
        assert mock_copy.called
        assert "Copied to clipboard" in result.output


def test_standup_no_note_found(tmp_path):
    daily_dir = tmp_path / DAILY_FOLDER
    daily_dir.mkdir()

    with patch("obsmind.commands.standup.load_config", return_value={"daily_notes_folder": DAILY_FOLDER}), \
         patch("obsmind.commands.standup.resolve_vault_path", return_value=tmp_path):

        result = runner.invoke(app, ["standup"])
        assert result.exit_code == 1
        assert "No daily note found" in result.output


def test_standup_falls_back_to_older_note(tmp_path):
    daily_dir = tmp_path / DAILY_FOLDER
    daily_dir.mkdir()
    two_days_ago = (datetime.today() - timedelta(days=2)).strftime("%Y-%m-%d")
    (daily_dir / f"{two_days_ago}.md").write_text(DAILY_CONTENT)

    with patch("obsmind.commands.standup.load_config", return_value={"daily_notes_folder": DAILY_FOLDER}), \
         patch("obsmind.commands.standup.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.standup.find_project_notes", return_value=[]), \
         patch("obsmind.commands.standup.load_context", return_value="ctx"), \
         patch("obsmind.commands.standup.ai_core.call", return_value=_fake_resp()):

        result = runner.invoke(app, ["standup", "--days", "3"])
        assert result.exit_code == 0
        assert "Done" in result.output


def test_standup_vault_error():
    with patch("obsmind.commands.standup.load_config", return_value={}), \
         patch("obsmind.commands.standup.resolve_vault_path", side_effect=FileNotFoundError("vault not found")):

        result = runner.invoke(app, ["standup"])
        assert result.exit_code == 1
        assert "vault not found" in result.output


def test_standup_uses_haiku(tmp_path):
    daily_dir = tmp_path / DAILY_FOLDER
    daily_dir.mkdir()
    (daily_dir / f"{YESTERDAY}.md").write_text(DAILY_CONTENT)

    with patch("obsmind.commands.standup.load_config", return_value={"daily_notes_folder": DAILY_FOLDER}), \
         patch("obsmind.commands.standup.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.standup.find_project_notes", return_value=[]), \
         patch("obsmind.commands.standup.load_context", return_value="ctx"), \
         patch("obsmind.commands.standup.ai_core.call", return_value=_fake_resp()) as mock_call:

        runner.invoke(app, ["standup"])
        task = mock_call.call_args[1].get("task") or mock_call.call_args[0][0]
        assert task == "standup"
