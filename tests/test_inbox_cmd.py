"""Tests for commands/inbox.py."""

from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from obsmind.cli import app
from obsmind.core.ai import AIResponse
from obsmind.commands.inbox import _collect_captures, _parse_routes, CaptureItem

runner   = CliRunner()
VAULT    = Path("/fake/vault")
YESTERDAY = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

DAILY_WITH_CAPTURES = f"""\
## Quick Capture

- finished the auth module
- need to look into Redis caching for DeckForge
- book dentist appointment

## Focus Areas
- Worked on backend
"""

ROUTES_JSON = """[
  {"item": "finished the auth module", "action": "append", "destination": "Backend Architecture", "reason": "Completed backend task"},
  {"item": "need to look into Redis caching for DeckForge", "action": "append", "destination": "DeckForge", "reason": "DeckForge performance task"},
  {"item": "book dentist appointment", "action": "create", "destination": "Health Tasks", "reason": "Personal health item"}
]"""


def _fake_resp(content: str = ROUTES_JSON) -> AIResponse:
    return AIResponse(
        content=content,
        model="claude-sonnet-4-6",
        task="inbox_route",
        input_tokens=300,
        output_tokens=200,
        cost_usd=0.005,
        elapsed_ms=400,
    )


# ── unit: _collect_captures ───────────────────────────────────────────────

def test_collect_captures_extracts_items(tmp_path):
    daily_dir = tmp_path / "Daily Notes"
    daily_dir.mkdir()
    note = daily_dir / f"{YESTERDAY}.md"
    note.write_text(DAILY_WITH_CAPTURES)

    from obsmind.core.vault import read_note as real_read
    items = _collect_captures([(YESTERDAY, note)])
    texts = [i.text for i in items]

    assert "finished the auth module" in texts
    assert "need to look into Redis caching for DeckForge" in texts
    assert "book dentist appointment" in texts


def test_collect_captures_skips_processed(tmp_path):
    daily_dir = tmp_path / "Daily Notes"
    daily_dir.mkdir()
    note = daily_dir / f"{YESTERDAY}.md"
    note.write_text("## Quick Capture\n\n- ~~already done~~\n- still todo\n")

    items = _collect_captures([(YESTERDAY, note)])
    texts = [i.text for i in items]

    assert "already done" not in texts
    assert "still todo" in texts


def test_collect_captures_skips_empty_sections(tmp_path):
    daily_dir = tmp_path / "Daily Notes"
    daily_dir.mkdir()
    note = daily_dir / f"{YESTERDAY}.md"
    note.write_text("## Quick Capture\n\n## Focus Areas\n- something\n")

    items = _collect_captures([(YESTERDAY, note)])
    assert len(items) == 0


# ── unit: _parse_routes ───────────────────────────────────────────────────

def test_parse_routes_valid():
    routes = _parse_routes(ROUTES_JSON)
    assert len(routes) == 3
    assert routes[0]["action"] == "append"
    assert routes[0]["destination"] == "Backend Architecture"


def test_parse_routes_empty_array():
    assert _parse_routes("[]") == []


def test_parse_routes_bad_json():
    assert _parse_routes("not json at all") == []


# ── integration: command ──────────────────────────────────────────────────

def test_inbox_dry_run_shows_table(tmp_path):
    daily_dir = tmp_path / "Daily Notes"
    daily_dir.mkdir()
    (daily_dir / f"{YESTERDAY}.md").write_text(DAILY_WITH_CAPTURES)

    with patch("obsmind.commands.inbox.load_config", return_value={"daily_notes_folder": "Daily Notes"}), \
         patch("obsmind.commands.inbox.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.inbox.iter_notes", return_value=[]), \
         patch("obsmind.commands.inbox.load_context", return_value="ctx"), \
         patch("obsmind.commands.inbox.ai_core.call", return_value=_fake_resp()):

        result = runner.invoke(app, ["inbox", "--dry-run"])
        assert result.exit_code == 0
        assert "DeckForge" in result.output
        assert "Health Tasks" in result.output
        assert "Dry run" in result.output


def test_inbox_empty_capture(tmp_path):
    daily_dir = tmp_path / "Daily Notes"
    daily_dir.mkdir()
    (daily_dir / f"{YESTERDAY}.md").write_text("## Quick Capture\n\n## Focus Areas\n")

    with patch("obsmind.commands.inbox.load_config", return_value={"daily_notes_folder": "Daily Notes"}), \
         patch("obsmind.commands.inbox.resolve_vault_path", return_value=tmp_path):

        result = runner.invoke(app, ["inbox"])
        assert "Quick Capture is clear" in result.output
        assert result.exit_code == 0


def test_inbox_vault_error():
    with patch("obsmind.commands.inbox.load_config", return_value={}), \
         patch("obsmind.commands.inbox.resolve_vault_path", side_effect=FileNotFoundError("vault not found")):

        result = runner.invoke(app, ["inbox"])
        assert result.exit_code == 1
        assert "vault not found" in result.output


def test_inbox_routes_append_on_confirm(tmp_path):
    daily_dir = tmp_path / "Daily Notes"
    daily_dir.mkdir()
    (daily_dir / f"{YESTERDAY}.md").write_text(DAILY_WITH_CAPTURES)

    routes = '[{"item": "finished the auth module", "action": "append", "destination": "Backend", "reason": "done"}]'

    with patch("obsmind.commands.inbox.load_config", return_value={"daily_notes_folder": "Daily Notes"}), \
         patch("obsmind.commands.inbox.resolve_vault_path", return_value=tmp_path), \
         patch("obsmind.commands.inbox.iter_notes", return_value=[]), \
         patch("obsmind.commands.inbox.load_context", return_value="ctx"), \
         patch("obsmind.commands.inbox.ai_core.call", return_value=_fake_resp(routes)), \
         patch("obsmind.commands.inbox.Confirm.ask", return_value=True), \
         patch("obsmind.commands.inbox.append_to_note") as mock_append, \
         patch("obsmind.commands.inbox.rewrite_note"):

        result = runner.invoke(app, ["inbox"])
        assert mock_append.called
