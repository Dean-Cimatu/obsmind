"""Tests for commands/daily.py — Anthropic SDK and obs are fully mocked."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner

from obsmind.cli import app

runner = CliRunner()


# ── fixtures ───────────────────────────────────────────────────────────────

DAILY_CONTENT = """\
---
tags: [daily]
date: 2026-04-21
---

# Daily Note — Tuesday 21 April 2026

## Quick Capture

## Focus Areas

## Tasks

| Task | Status |
| ---- | ------ |

## University & Studies

## Projects

## Reflection

## Learning Log
"""


@pytest.fixture
def tmp_vault(tmp_path):
    vault = tmp_path / "vault"
    daily_dir = vault / "Daily Notes"
    daily_dir.mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    note = daily_dir / "2026-04-21.md"
    note.write_text(DAILY_CONTENT)
    return vault, note


@pytest.fixture
def mock_env(tmp_vault, tmp_path, mocker):
    vault, note = tmp_vault
    cfg = {
        "vault_path":         str(vault),
        "profile":            "dev",
        "daily_notes_folder": "Daily Notes",
        "context_notes":      [],
        "priorities_note":    "",
    }
    mocker.patch("obsmind.commands.daily.load_config",    return_value=cfg)
    mocker.patch("obsmind.commands.daily.resolve_vault_path", return_value=vault)
    mocker.patch("obsmind.commands.daily.load_context",   return_value="test context")
    mocker.patch("obsmind.core.context.CONTEXT_FILE",     tmp_path / "context.md")
    mocker.patch("obsmind.core.usage.USAGE_FILE",         tmp_path / "usage.jsonl")
    mocker.patch("obsmind.core.usage.USAGE_DIR",          tmp_path)
    # Freeze date so tests don't break the next day
    mocker.patch("obsmind.commands.daily.read_today_note", return_value=(DAILY_CONTENT, note))
    mocker.patch("obsmind.core.vault.datetime") .today.return_value.strftime.return_value = "2026-04-21"
    return vault, note


def make_ai_response(content="", input_tokens=50, output_tokens=30):
    from obsmind.core.ai import AIResponse, SONNET
    return AIResponse(
        content=content,
        model=SONNET,
        task="daily_update",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=0.00015,
        elapsed_ms=500,
    )


# ── --update: happy path ───────────────────────────────────────────────────

def test_update_routes_to_quick_capture(mock_env, mocker):
    vault, note = mock_env
    ai_json = json.dumps({"section": "Quick Capture", "text": "random thought", "confidence": 0.9})
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(ai_json))
    mock_add = mocker.patch("obsmind.commands.daily.daily_add")

    result = runner.invoke(app, ["daily", "--update", "random thought"], input="y\n")

    assert result.exit_code == 0
    mock_add.assert_called_once_with("Quick Capture", "random thought")


def test_update_routes_to_tasks(mock_env, mocker):
    vault, note = mock_env
    ai_json = json.dumps({"section": "Tasks", "text": "review Arctic Lake HR challenge", "confidence": 0.95})
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(ai_json))
    mock_add = mocker.patch("obsmind.commands.daily.daily_add")

    result = runner.invoke(app, ["daily", "--update", "todo: review Arctic Lake HR challenge"], input="y\n")

    assert result.exit_code == 0
    mock_add.assert_called_once_with("Tasks", "review Arctic Lake HR challenge")


def test_update_falls_back_on_low_confidence(mock_env, mocker):
    vault, note = mock_env
    ai_json = json.dumps({"section": "University & Studies", "text": "vague note", "confidence": 0.4})
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(ai_json))
    mock_add = mocker.patch("obsmind.commands.daily.daily_add")

    result = runner.invoke(app, ["daily", "--update", "random thought that fits nowhere"], input="y\n")

    assert result.exit_code == 0
    mock_add.assert_called_once_with("Quick Capture", "vague note")
    assert "No clear section" in result.output or "Quick Capture" in result.output


def test_update_falls_back_on_unknown_section(mock_env, mocker):
    vault, note = mock_env
    ai_json = json.dumps({"section": "Imaginary Section", "text": "some text", "confidence": 0.9})
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(ai_json))
    mock_add = mocker.patch("obsmind.commands.daily.daily_add")

    result = runner.invoke(app, ["daily", "--update", "some text"], input="y\n")

    assert result.exit_code == 0
    mock_add.assert_called_once_with("Quick Capture", "some text")


def test_update_aborted_on_n(mock_env, mocker):
    vault, note = mock_env
    ai_json = json.dumps({"section": "Quick Capture", "text": "thought", "confidence": 0.9})
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(ai_json))
    mock_add = mocker.patch("obsmind.commands.daily.daily_add")

    result = runner.invoke(app, ["daily", "--update", "thought"], input="n\n")

    assert result.exit_code == 0
    mock_add.assert_not_called()


# ── --update: error paths ──────────────────────────────────────────────────

def test_update_no_api_key(mock_env, mocker):
    vault, note = mock_env
    mocker.patch(
        "obsmind.commands.daily.ai_core.call",
        side_effect=EnvironmentError("ANTHROPIC_API_KEY is not set.\nFix: export ANTHROPIC_API_KEY=sk-ant-..."),
    )
    result = runner.invoke(app, ["daily", "--update", "test"])
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_update_obs_missing(mock_env, mocker):
    from obsmind.core.obsflow import ObsFlowNotFoundError
    vault, note = mock_env
    ai_json = json.dumps({"section": "Quick Capture", "text": "test", "confidence": 0.9})
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(ai_json))
    mocker.patch(
        "obsmind.commands.daily.daily_add",
        side_effect=ObsFlowNotFoundError("obs CLI not found in PATH.\nFix: install ObsFlow..."),
    )
    result = runner.invoke(app, ["daily", "--update", "test"], input="y\n")
    assert result.exit_code == 1
    assert "obs" in result.output.lower()


def test_update_no_daily_note(mock_env, mocker):
    vault, note = mock_env
    note.unlink()  # delete today's note
    result = runner.invoke(app, ["daily", "--update", "test"])
    assert result.exit_code == 1
    assert "daily" in result.output.lower() or "obs daily" in result.output


# ── --reflect ──────────────────────────────────────────────────────────────

def test_reflect_formats_and_writes(mock_env, mocker):
    vault, note = mock_env
    formatted = "**What went well:** ...\n**What to improve:** ...\n**Tomorrow's focus:** ..."
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(formatted))
    mock_add = mocker.patch("obsmind.commands.daily.daily_add")

    answers = "good work\nbetter focus\nfinish project\ny\n"
    result = runner.invoke(app, ["daily", "--reflect"], input=answers)

    assert result.exit_code == 0
    mock_add.assert_called_once()
    args = mock_add.call_args[0]
    assert args[0] == "Reflection"


def test_reflect_calls_ai_with_right_task(mock_env, mocker):
    vault, note = mock_env
    mocker.patch("obsmind.commands.daily.daily_add")
    ai_mock = mocker.patch(
        "obsmind.commands.daily.ai_core.call",
        return_value=make_ai_response("formatted reflection"),
    )

    runner.invoke(app, ["daily", "--reflect"], input="good\nbetter\nfocus\ny\n")

    call_kwargs = ai_mock.call_args
    assert call_kwargs[1]["task"] == "daily_reflect" or call_kwargs[0][0] == "daily_reflect"


# ── --fill ─────────────────────────────────────────────────────────────────

def test_fill_accepts_suggestions(mock_env, mocker):
    vault, note = mock_env
    suggestions = json.dumps(["Finish ObsMind stage 2", "Review open PRs", "Draft placement email"])
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(suggestions))
    mock_add = mocker.patch("obsmind.commands.daily.daily_add")
    mocker.patch("obsmind.commands.daily.find_daily_notes", return_value=[])
    mocker.patch("obsmind.commands.daily.find_project_notes", return_value=[])

    # Accept all 3
    result = runner.invoke(app, ["daily", "--fill"], input="y\ny\ny\n")

    assert result.exit_code == 0
    assert mock_add.call_count == 3
    for call in mock_add.call_args_list:
        assert call[0][0] == "Focus Areas"


def test_fill_rejects_suggestions(mock_env, mocker):
    vault, note = mock_env
    suggestions = json.dumps(["Entry A", "Entry B"])
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(suggestions))
    mock_add = mocker.patch("obsmind.commands.daily.daily_add")
    mocker.patch("obsmind.commands.daily.find_daily_notes", return_value=[])
    mocker.patch("obsmind.commands.daily.find_project_notes", return_value=[])

    # Reject first, accept second
    result = runner.invoke(app, ["daily", "--fill"], input="n\ny\n")

    assert result.exit_code == 0
    assert mock_add.call_count == 1
    assert mock_add.call_args[0][1] == "Entry B"


# ── daily summary ──────────────────────────────────────────────────────────

def test_summary_no_writes(mock_env, mocker):
    vault, note = mock_env
    summary_text = "**What got done**\n- Fixed bug\n\n**Still open**\n- PR review\n\n**Inferred mood**\nFocused."
    mocker.patch("obsmind.commands.daily.ai_core.call", return_value=make_ai_response(summary_text))
    mock_add = mocker.patch("obsmind.commands.daily.daily_add")

    result = runner.invoke(app, ["daily", "summary"])

    assert result.exit_code == 0
    mock_add.assert_not_called()
    assert "Fixed bug" in result.output or "What got done" in result.output


def test_summary_uses_haiku(mock_env, mocker):
    vault, note = mock_env
    ai_mock = mocker.patch(
        "obsmind.commands.daily.ai_core.call",
        return_value=make_ai_response("summary"),
    )
    runner.invoke(app, ["daily", "summary"])
    call_args = ai_mock.call_args
    task = call_args[1].get("task") or call_args[0][0]
    assert task == "daily_summary"


# ── usage logging ──────────────────────────────────────────────────────────

def test_update_logs_usage(mock_env, mocker, tmp_path):
    vault, note = mock_env
    usage_file = tmp_path / "usage.jsonl"
    mocker.patch("obsmind.core.usage.USAGE_FILE", usage_file)
    mocker.patch("obsmind.core.usage.USAGE_DIR",  tmp_path)

    ai_json = json.dumps({"section": "Quick Capture", "text": "test", "confidence": 0.9})
    mocker.patch("obsmind.commands.daily.daily_add")

    # Call ai.call for real (mocking just the anthropic client)
    mock_client = MagicMock()
    msg = MagicMock()
    msg.usage.input_tokens = 50
    msg.usage.output_tokens = 30
    msg.content = [MagicMock(text=ai_json)]
    mock_client.messages.create.return_value = msg
    mocker.patch("obsmind.core.ai._client", return_value=mock_client)

    result = runner.invoke(app, ["daily", "--update", "test thought"], input="y\n")

    assert result.exit_code == 0
    assert usage_file.exists()
    record = json.loads(usage_file.read_text().strip().splitlines()[-1])
    assert record["command"] == "daily --update"
    assert record["input_tokens"] == 50
