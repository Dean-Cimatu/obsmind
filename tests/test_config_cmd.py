"""Smoke tests for commands/config.py using Typer test client."""

import json
import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock

from obsmind.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def tmp_config(tmp_path, mocker):
    """Redirect config and context files to temp locations."""
    mocker.patch("obsmind.core.vault.STATE_DIR",  tmp_path / ".obsmind")
    mocker.patch("obsmind.core.vault.CONFIG_FILE", tmp_path / ".obsmind" / "config.json")
    mocker.patch("obsmind.core.context.CONTEXT_FILE", tmp_path / "context.md")


# ── --version ─────────────────────────────────────────────────────────────

def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "ObsMind" in result.output


# ── config show ────────────────────────────────────────────────────────────

def test_config_show(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test12345")
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "sk-ant-" in result.output
    assert "vault_path" in result.output


def test_config_show_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "not set" in result.output


# ── config set ─────────────────────────────────────────────────────────────

def test_config_set_valid_key(tmp_path, mocker):
    cfg_file = tmp_path / ".obsmind" / "config.json"
    mocker.patch("obsmind.core.vault.CONFIG_FILE", cfg_file)
    mocker.patch("obsmind.core.vault.STATE_DIR",   tmp_path / ".obsmind")
    result = runner.invoke(app, ["config", "set", "profile", "writer"])
    assert result.exit_code == 0
    assert "profile" in result.output


def test_config_set_invalid_key():
    result = runner.invoke(app, ["config", "set", "nonexistent_key", "val"])
    assert result.exit_code != 0
    assert "Unknown key" in result.output


# ── profile show / set ─────────────────────────────────────────────────────

def test_profile_show():
    result = runner.invoke(app, ["profile", "show"])
    assert result.exit_code == 0
    assert "dev" in result.output


def test_profile_set_dev(tmp_path, mocker):
    cfg_file = tmp_path / ".obsmind" / "config.json"
    mocker.patch("obsmind.core.vault.CONFIG_FILE", cfg_file)
    mocker.patch("obsmind.core.vault.STATE_DIR",   tmp_path / ".obsmind")
    result = runner.invoke(app, ["profile", "set", "dev"])
    assert result.exit_code == 0


def test_profile_set_unknown():
    result = runner.invoke(app, ["profile", "set", "writer"])
    assert result.exit_code != 0
    assert "dev profile" in result.output.lower() or "not implemented" in result.output.lower()


# ── usage ──────────────────────────────────────────────────────────────────

def test_usage_empty(mocker):
    mocker.patch("obsmind.core.usage.USAGE_FILE", __import__('pathlib').Path("/nonexistent/usage.jsonl"))
    result = runner.invoke(app, ["usage"])
    assert result.exit_code == 0
    assert "No API calls" in result.output


# ── context show ───────────────────────────────────────────────────────────

def test_context_show_missing(tmp_path, mocker):
    mocker.patch("obsmind.core.context.CONTEXT_FILE", tmp_path / "nonexistent.md")
    result = runner.invoke(app, ["context", "show"])
    assert result.exit_code != 0
    assert "context update" in result.output.lower() or "No context" in result.output
