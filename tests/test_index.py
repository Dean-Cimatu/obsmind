"""Tests for core/index.py."""

import json
import pytest
from pathlib import Path


@pytest.fixture
def vault_with_index(tmp_path):
    vault = tmp_path / "vault"
    obsflow_dir = vault / ".obsflow"
    obsflow_dir.mkdir(parents=True)
    return vault


def write_index(vault, data):
    (vault / ".obsflow" / "index.json").write_text(json.dumps(data))


VALID_INDEX = {
    "builtAt": "2026-04-21T00:00:00Z",
    "elapsed": 42,
    "notes": {
        "A.md": {
            "path": "A.md", "title": "Alpha", "aliases": [],
            "tags": ["test"], "outgoingLinks": ["Beta"],
            "incomingLinks": [], "modified": 0, "wordCount": 10,
        },
        "B.md": {
            "path": "B.md", "title": "Beta", "aliases": [],
            "tags": [], "outgoingLinks": [],
            "incomingLinks": ["A.md"], "modified": 0, "wordCount": 5,
        },
    },
}


def test_load_index_valid(vault_with_index):
    write_index(vault_with_index, VALID_INDEX)
    from obsmind.core.index import load_index
    idx = load_index(vault_with_index)
    assert "notes" in idx
    assert "builtAt" in idx


def test_load_index_missing(tmp_path):
    from obsmind.core.index import load_index, IndexError
    with pytest.raises(IndexError, match="not found"):
        load_index(tmp_path / "empty_vault")


def test_load_index_corrupt(vault_with_index):
    (vault_with_index / ".obsflow" / "index.json").write_text("not json{{{")
    from obsmind.core.index import load_index, IndexError
    with pytest.raises(IndexError, match="corrupt"):
        load_index(vault_with_index)


def test_load_index_missing_keys(vault_with_index):
    write_index(vault_with_index, {"notes": {}})
    from obsmind.core.index import load_index, IndexError
    with pytest.raises(IndexError, match="missing keys"):
        load_index(vault_with_index)


def test_get_titles(vault_with_index):
    write_index(vault_with_index, VALID_INDEX)
    from obsmind.core.index import load_index, get_titles
    idx = load_index(vault_with_index)
    titles = get_titles(idx)
    assert "Alpha" in titles
    assert "Beta" in titles


def test_stats(vault_with_index):
    write_index(vault_with_index, VALID_INDEX)
    from obsmind.core.index import load_index, stats
    idx = load_index(vault_with_index)
    s = stats(idx)
    assert s["note_count"] == 2
    assert s["link_count"] == 1
    assert s["word_count"] == 15
