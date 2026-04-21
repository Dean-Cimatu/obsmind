"""Tests for core/vault.py."""

import json
import pytest
from pathlib import Path


@pytest.fixture
def tmp_vault(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    return vault


@pytest.fixture
def note(tmp_vault):
    def _note(rel, content):
        p = tmp_vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p
    return _note


# ── resolve_vault_path ─────────────────────────────────────────────────────

def test_resolve_vault_path_from_config(tmp_vault):
    from obsmind.core.vault import resolve_vault_path
    cfg = {"vault_path": str(tmp_vault)}
    assert resolve_vault_path(cfg) == tmp_vault


def test_resolve_vault_path_falls_back_to_obsflow(tmp_vault, tmp_path, mocker):
    obsflow_rc = tmp_path / ".obsflowrc"
    obsflow_rc.write_text(json.dumps({"vaultPath": str(tmp_vault)}))
    mocker.patch("obsmind.core.vault.OBSFLOW_RC", obsflow_rc)
    from obsmind.core.vault import resolve_vault_path
    cfg = {"vault_path": ""}
    assert resolve_vault_path(cfg) == tmp_vault


def test_resolve_vault_path_raises_when_nothing(mocker):
    mocker.patch("obsmind.core.vault.OBSFLOW_RC", Path("/nonexistent/.obsflowrc"))
    from obsmind.core.vault import resolve_vault_path
    with pytest.raises(FileNotFoundError, match="Cannot find vault"):
        resolve_vault_path({"vault_path": ""})


# ── read_note ──────────────────────────────────────────────────────────────

def test_read_note_with_frontmatter(note):
    p = note("A.md", "---\ntitle: Alpha\ntags:\n  - test\n---\n# Alpha\n\nbody text\n")
    from obsmind.core.vault import read_note
    meta, body = read_note(p)
    assert meta["title"] == "Alpha"
    assert "test" in meta["tags"]
    assert "body text" in body


def test_read_note_without_frontmatter(note):
    p = note("B.md", "# Just a heading\n\nsome content\n")
    from obsmind.core.vault import read_note
    meta, body = read_note(p)
    assert meta == {}
    assert "some content" in body


# ── iter_notes ─────────────────────────────────────────────────────────────

def test_iter_notes_excludes_hidden(note, tmp_vault):
    note("visible.md", "# V")
    note(".obsidian/template.md", "# hidden")
    from obsmind.core.vault import iter_notes
    paths = iter_notes(tmp_vault)
    names = [p.name for p in paths]
    assert "visible.md" in names
    assert "template.md" not in names


# ── find_project_notes ─────────────────────────────────────────────────────

def test_find_project_notes_by_folder(note, tmp_vault):
    note("Projects/ObsFlow.md", "# ObsFlow")
    note("Notes/random.md", "# Random")
    from obsmind.core.vault import find_project_notes
    projs = find_project_notes(tmp_vault)
    assert any(p.name == "ObsFlow.md" for p in projs)
    assert not any(p.name == "random.md" for p in projs)


def test_find_project_notes_by_tag(note, tmp_vault):
    note("tagged.md", "---\ntags:\n  - project\n---\n# Tagged")
    from obsmind.core.vault import find_project_notes
    projs = find_project_notes(tmp_vault)
    assert any(p.name == "tagged.md" for p in projs)


# ── find_note_by_title ─────────────────────────────────────────────────────

def test_find_note_by_title_found(note, tmp_vault):
    note("MyNote.md", "# My Note")
    from obsmind.core.vault import find_note_by_title
    p = find_note_by_title(tmp_vault, "MyNote")
    assert p is not None
    assert p.name == "MyNote.md"


def test_find_note_by_title_missing(tmp_vault):
    from obsmind.core.vault import find_note_by_title
    assert find_note_by_title(tmp_vault, "Ghost") is None
