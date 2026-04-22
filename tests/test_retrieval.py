"""Tests for core/retrieval.py — keyword scoring and link boost."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obsmind.core.retrieval import (
    _query_terms,
    _tokenise,
    _extract_links,
    _score_note,
    retrieve,
    format_for_prompt,
    ScoredNote,
)


# ── unit helpers ──────────────────────────────────────────────────────────

def test_tokenise_basic():
    assert _tokenise("Hello World!") == ["hello", "world"]


def test_tokenise_numbers():
    assert "42" in _tokenise("chapter 42")


def test_query_terms_removes_stopwords():
    terms = _query_terms("what are the best practices for Python")
    assert "what" not in terms
    assert "the" not in terms
    assert "are" not in terms
    assert "best" in terms
    assert "python" in terms


def test_query_terms_min_length():
    terms = _query_terms("go to the AI lab")
    assert "go" not in terms  # < 3 chars
    assert "lab" in terms


def test_extract_links():
    content = "See [[ProjectAlpha]] and [[Beta Notes|alias]] for details."
    links = _extract_links(content)
    assert "projectalpha" in links
    assert "beta notes" in links


def test_score_note_title_match(tmp_path):
    note = tmp_path / "Machine Learning.md"
    note.write_text("")
    score, matched = _score_note(note, ["machine", "learning"], tags=[], content_preview="")
    assert score > 0
    assert "machine" in matched
    assert "learning" in matched


def test_score_note_tag_match(tmp_path):
    note = tmp_path / "Notes.md"
    note.write_text("")
    score, matched = _score_note(note, ["python"], tags=["python", "tutorial"], content_preview="")
    assert score > 0
    assert "python" in matched


def test_score_note_content_match(tmp_path):
    note = tmp_path / "Notes.md"
    note.write_text("")
    score, matched = _score_note(note, ["neural"], tags=[], content_preview="neural networks are fascinating")
    assert score > 0
    assert "neural" in matched


# ── retrieve integration ──────────────────────────────────────────────────

def _make_vault(tmp_path, notes: dict[str, tuple[dict, str]]) -> Path:
    """Create temp vault with {filename: (meta, body)} pairs."""
    vault = tmp_path / "vault"
    vault.mkdir()
    for name, (meta, body) in notes.items():
        tags = meta.get("tags", [])
        fm = "---\ntags:\n" + "".join(f"  - {t}\n" for t in tags) + "---\n" if tags else ""
        (vault / f"{name}.md").write_text(fm + body)
    return vault


def test_retrieve_returns_relevant(tmp_path):
    vault = _make_vault(tmp_path, {
        "Python Tutorial": ({}, "python programming basics"),
        "Cooking Recipes": ({}, "how to bake bread"),
        "ML Notes": ({"tags": ["python", "ml"]}, "machine learning with python"),
    })

    results = retrieve(vault, "python machine learning", limit=5)
    titles = [r.title for r in results]
    assert "ML Notes" in titles
    assert "Python Tutorial" in titles
    assert "Cooking Recipes" not in titles


def test_retrieve_respects_limit(tmp_path):
    vault = _make_vault(tmp_path, {
        f"Note{i}": ({}, f"python relevance score {i}") for i in range(10)
    })
    results = retrieve(vault, "python relevance", limit=3)
    assert len(results) <= 3


def test_retrieve_empty_query(tmp_path):
    vault = _make_vault(tmp_path, {"Note": ({}, "content")})
    results = retrieve(vault, "the and for", limit=5)  # all stopwords
    assert results == []


def test_retrieve_sorted_by_score(tmp_path):
    vault = _make_vault(tmp_path, {
        "Python Basics": ({}, "python programming"),           # title match
        "General Notes": ({}, "i once mentioned python here"), # content match only
    })
    results = retrieve(vault, "python", limit=5)
    assert len(results) >= 2
    assert results[0].score >= results[1].score


# ── format_for_prompt ─────────────────────────────────────────────────────

def test_format_for_prompt_empty():
    assert "no relevant" in format_for_prompt([])


def test_format_for_prompt_includes_title(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    note_path = vault / "My Note.md"
    note_path.write_text("some content here")

    scored = ScoredNote(path=note_path, title="My Note", score=3.0, matched_terms=["test"])
    block = format_for_prompt([scored], max_chars_each=50)
    assert "My Note" in block
    assert "score" in block.lower()
