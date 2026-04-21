"""Tests for core/context.py."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock


@pytest.fixture
def tmp_vault(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    return vault


def make_note(vault, rel, content):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_build_context_empty_vault(tmp_vault, tmp_path, mocker):
    mocker.patch("obsmind.core.context.CONTEXT_FILE", tmp_path / "context.md")
    cfg = {"vault_path": str(tmp_vault), "profile": "dev",
           "daily_notes_folder": "Daily Notes", "context_notes": [], "priorities_note": ""}
    from obsmind.core.context import build_context
    result = build_context(cfg)
    assert "ObsMind Context" in result


def test_build_context_includes_project_notes(tmp_vault, tmp_path, mocker):
    make_note(tmp_vault, "Projects/ObsFlow.md", "# ObsFlow\n\nAmazing tool\n")
    mocker.patch("obsmind.core.context.CONTEXT_FILE", tmp_path / "context.md")
    cfg = {"vault_path": str(tmp_vault), "profile": "dev",
           "daily_notes_folder": "Daily Notes", "context_notes": [], "priorities_note": ""}
    from obsmind.core.context import build_context
    result = build_context(cfg)
    assert "ObsFlow" in result
    assert "Amazing tool" in result


def test_update_context_writes_file(tmp_vault, tmp_path, mocker):
    cache = tmp_path / "context.md"
    mocker.patch("obsmind.core.context.CONTEXT_FILE", cache)
    cfg = {"vault_path": str(tmp_vault), "profile": "dev",
           "daily_notes_folder": "Daily Notes", "context_notes": [], "priorities_note": ""}
    from obsmind.core.context import update_context
    path = update_context(cfg)
    assert path == cache
    assert cache.exists()
    assert "ObsMind Context" in cache.read_text()


def test_load_context_returns_none_when_missing(tmp_path, mocker):
    mocker.patch("obsmind.core.context.CONTEXT_FILE", tmp_path / "nonexistent.md")
    from obsmind.core.context import load_context
    assert load_context() is None


def test_load_context_returns_content(tmp_path, mocker):
    cache = tmp_path / "context.md"
    cache.write_text("# My Context\n")
    mocker.patch("obsmind.core.context.CONTEXT_FILE", cache)
    from obsmind.core.context import load_context
    assert load_context() == "# My Context\n"


def test_system_prompt_contains_base_text(tmp_path, mocker):
    mocker.patch("obsmind.core.context.CONTEXT_FILE", tmp_path / "nonexistent.md")
    cfg = {"vault_path": "", "profile": "dev",
           "daily_notes_folder": "Daily Notes", "context_notes": [], "priorities_note": ""}
    mocker.patch("obsmind.core.context.load_config", return_value=cfg)
    from obsmind.core.context import system_prompt
    sp = system_prompt(cfg)
    assert "ObsMind" in sp
    assert "wikilink" in sp
