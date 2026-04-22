"""Tests for commands/ask.py — ask and find commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from obsmind.cli import app
from obsmind.core.ai import AIResponse
from obsmind.core.retrieval import ScoredNote

runner = CliRunner()

VAULT_PATH = Path("/fake/vault")


def _fake_resp(content: str, task: str = "ask") -> AIResponse:
    return AIResponse(
        content=content,
        model="claude-sonnet-4-6",
        task=task,
        input_tokens=200,
        output_tokens=100,
        cost_usd=0.002,
        elapsed_ms=300,
    )


def _fake_notes(n: int = 3) -> list[ScoredNote]:
    return [
        ScoredNote(
            path=VAULT_PATH / f"Note{i}.md",
            title=f"Note{i}",
            score=float(n - i),
            matched_terms=["test"],
        )
        for i in range(n)
    ]


# ── ask ───────────────────────────────────────────────────────────────────

def test_ask_shows_answer():
    with patch("obsmind.commands.ask.load_config", return_value={}), \
         patch("obsmind.commands.ask.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.ask.retrieve", return_value=_fake_notes(3)), \
         patch("obsmind.commands.ask.load_context", return_value="user context"), \
         patch("obsmind.commands.ask.ai_core.call", return_value=_fake_resp("The answer is [[Note0]].")):

        result = runner.invoke(app, ["ask", "What is the project about?"])
        assert "The answer is" in result.output
        assert result.exit_code == 0


def test_ask_no_results():
    with patch("obsmind.commands.ask.load_config", return_value={}), \
         patch("obsmind.commands.ask.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.ask.retrieve", return_value=[]):

        result = runner.invoke(app, ["ask", "query with no matches"])
        assert "No relevant notes" in result.output
        assert result.exit_code == 0


def test_ask_opus_flag_escalates():
    with patch("obsmind.commands.ask.load_config", return_value={}), \
         patch("obsmind.commands.ask.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.ask.retrieve", return_value=_fake_notes(3)), \
         patch("obsmind.commands.ask.load_context", return_value="ctx"), \
         patch("obsmind.commands.ask.ai_core.call", return_value=_fake_resp("answer", "ask_opus")) as mock_call:

        runner.invoke(app, ["ask", "question here", "--opus"])
        task_used = mock_call.call_args[1].get("task") or mock_call.call_args[0][0]
        assert task_used == "ask_opus"


def test_ask_auto_escalates_analytical():
    with patch("obsmind.commands.ask.load_config", return_value={}), \
         patch("obsmind.commands.ask.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.ask.retrieve", return_value=_fake_notes(3)), \
         patch("obsmind.commands.ask.load_context", return_value="ctx"), \
         patch("obsmind.commands.ask.ai_core.call", return_value=_fake_resp("answer", "ask_opus")) as mock_call:

        runner.invoke(app, ["ask", "compare all my project notes"])
        task_used = mock_call.call_args[1].get("task") or mock_call.call_args[0][0]
        assert task_used == "ask_opus"


def test_ask_vault_error():
    with patch("obsmind.commands.ask.load_config", return_value={}), \
         patch("obsmind.commands.ask.resolve_vault_path", side_effect=FileNotFoundError("vault not found")):

        result = runner.invoke(app, ["ask", "question"])
        assert result.exit_code == 1
        assert "vault not found" in result.output


# ── find ──────────────────────────────────────────────────────────────────

def test_find_shows_table():
    ranked_json = '[{"title": "Note0", "score": 0.9, "reason": "highly relevant"}]'
    with patch("obsmind.commands.ask.load_config", return_value={}), \
         patch("obsmind.commands.ask.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.ask.retrieve", return_value=_fake_notes(3)), \
         patch("obsmind.commands.ask.ai_core.call", return_value=_fake_resp(ranked_json, "find")):

        result = runner.invoke(app, ["find", "project planning"])
        assert "Note0" in result.output
        assert result.exit_code == 0


def test_find_no_results():
    with patch("obsmind.commands.ask.load_config", return_value={}), \
         patch("obsmind.commands.ask.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.ask.retrieve", return_value=[]):

        result = runner.invoke(app, ["find", "nonexistent topic"])
        assert "No candidates" in result.output
        assert result.exit_code == 0


def test_find_falls_back_on_bad_json():
    with patch("obsmind.commands.ask.load_config", return_value={}), \
         patch("obsmind.commands.ask.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.ask.retrieve", return_value=_fake_notes(3)), \
         patch("obsmind.commands.ask.ai_core.call", return_value=_fake_resp("not json at all", "find")):

        result = runner.invoke(app, ["find", "some query"])
        # Should fall back to keyword order — still shows a table
        assert result.exit_code == 0


def test_find_respects_limit():
    with patch("obsmind.commands.ask.load_config", return_value={}), \
         patch("obsmind.commands.ask.resolve_vault_path", return_value=VAULT_PATH), \
         patch("obsmind.commands.ask.retrieve", return_value=_fake_notes(5)) as mock_retrieve, \
         patch("obsmind.commands.ask.ai_core.call", return_value=_fake_resp(
             '[{"title": "Note0", "score": 0.9, "reason": "top"}, '
             '{"title": "Note1", "score": 0.7, "reason": "good"}]',
             "find"
         )):

        result = runner.invoke(app, ["find", "topic", "--limit", "2"])
        assert result.exit_code == 0
