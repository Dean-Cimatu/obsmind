"""Keyword-based retrieval for vault notes.

Scores notes by keyword overlap and link neighbourhood — no embeddings,
no network calls. Designed to run fast enough to be a synchronous pre-filter
before sending the top-N to Claude.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .vault import iter_notes, read_note

# Regex to extract [[wikilinks]] from note content
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]")

# Weight constants
_W_TITLE   = 3.0
_W_TAG     = 2.0
_W_CONTENT = 1.0
_W_LINK    = 0.5   # boost when candidates link to each other


@dataclass
class ScoredNote:
    path: Path
    title: str
    score: float
    matched_terms: list[str] = field(default_factory=list)

    def preview(self, max_chars: int = 300) -> str:
        try:
            _, body = read_note(self.path)
            return body.strip()[:max_chars]
        except Exception:
            return ""


def _tokenise(text: str) -> list[str]:
    """Lowercase words, strip punctuation."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _query_terms(query: str) -> list[str]:
    """Extract meaningful terms from a query (≥3 chars, no stopwords)."""
    _STOP = {
        "the", "and", "for", "that", "this", "with", "from", "are",
        "was", "were", "has", "have", "had", "its", "how", "what",
        "when", "where", "who", "why", "can", "could", "would",
        "should", "about", "into", "than", "then",
    }
    return [t for t in _tokenise(query) if len(t) >= 3 and t not in _STOP]


def _extract_links(content: str) -> set[str]:
    """Return lowercased wikilink targets from note content."""
    return {m.group(1).strip().lower() for m in _WIKILINK_RE.finditer(content)}


def _score_note(
    path: Path,
    terms: list[str],
    *,
    tags: list[str],
    content_preview: str,
) -> tuple[float, list[str]]:
    title_tokens   = _tokenise(path.stem)
    tag_tokens     = _tokenise(" ".join(tags))
    content_tokens = _tokenise(content_preview[:2000])

    matched: list[str] = []
    score = 0.0

    for term in terms:
        in_title   = term in title_tokens
        in_tags    = term in tag_tokens
        in_content = term in content_tokens

        if in_title:
            score += _W_TITLE
        if in_tags:
            score += _W_TAG
        if in_content:
            score += _W_CONTENT

        if in_title or in_tags or in_content:
            matched.append(term)

    return score, matched


def retrieve(
    vault_path: Path,
    query: str,
    limit: int = 5,
) -> list[ScoredNote]:
    """Return the top `limit` notes most relevant to `query`.

    Scoring:
      - title word match: +3 per term
      - tag match:        +2 per term
      - content match:    +1 per term
      - link boost:       +0.5 when a candidate links to another candidate

    Returns notes sorted by descending score, score > 0 only.
    """
    terms = _query_terms(query)
    if not terms:
        return []

    candidates: list[ScoredNote] = []
    link_map: dict[str, set[str]] = {}  # title_lower -> set of linked title_lower

    for path in iter_notes(vault_path):
        try:
            meta, body = read_note(path)
        except Exception:
            continue

        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = tags.split()
        tags = [str(t) for t in tags if t is not None]

        score, matched = _score_note(
            path,
            terms,
            tags=tags,
            content_preview=body,
        )

        if score > 0:
            candidates.append(ScoredNote(path=path, title=path.stem, score=score, matched_terms=matched))

        link_map[path.stem.lower()] = _extract_links(body)

    # Link-neighbourhood boost: candidates that link to other candidates
    candidate_titles = {c.title.lower() for c in candidates}
    for c in candidates:
        links = link_map.get(c.title.lower(), set())
        boost = sum(_W_LINK for linked in links if linked in candidate_titles)
        c.score += boost

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:limit]


def format_for_prompt(notes: list[ScoredNote], max_chars_each: int = 600) -> str:
    """Format retrieved notes as a block for injection into a prompt."""
    if not notes:
        return "(no relevant notes found)"
    blocks = []
    for i, note in enumerate(notes, 1):
        preview = note.preview(max_chars_each)
        blocks.append(
            f"### [{i}] {note.title}\n"
            f"_(score: {note.score:.1f}, matched: {', '.join(note.matched_terms)})_\n\n"
            f"{preview}"
        )
    return "\n\n---\n\n".join(blocks)
