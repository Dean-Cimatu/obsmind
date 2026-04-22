"""Read-only section extraction from Obsidian markdown notes.

Parses H2 sections (## Header) from note content. Never writes.
"""

import re
from dataclasses import dataclass

# Sections in the ObsFlow daily template (used for fallback/validation)
DAILY_SECTIONS = [
    "Quick Capture",
    "Focus Areas",
    "Tasks",
    "University & Studies",
    "CS Academic Society",
    "Formula Student AI",
    "Placement Search",
    "Projects",
    "Learning Log",
    "Reflection",
    "Links",
]

_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)


@dataclass
class Section:
    name: str
    content: str        # full content of the section (may be empty)
    line_start: int     # 0-based line index of the ## header
    line_end: int       # exclusive end line index

    @property
    def preview(self) -> str:
        """First non-empty line of section content, truncated to 120 chars."""
        for line in self.content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("|"):
                return stripped[:120]
        return "(empty)"

    @property
    def is_empty(self) -> bool:
        stripped = self.content.strip()
        # A table-only section (Tasks) with only the header row counts as empty
        lines = [l for l in stripped.splitlines() if l.strip() and not l.strip().startswith("|") and not l.strip().startswith("-")]
        return not bool(stripped) or not lines


def parse_sections(content: str) -> list[Section]:
    """Return all H2 sections in a markdown note, in order."""
    lines = content.splitlines()
    headers: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        m = _H2_RE.match(line)
        if m:
            headers.append((i, m.group(1).strip()))

    sections: list[Section] = []
    for idx, (line_start, name) in enumerate(headers):
        line_end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        body_lines = lines[line_start + 1 : line_end]
        sections.append(Section(
            name=name,
            content="\n".join(body_lines),
            line_start=line_start,
            line_end=line_end,
        ))

    return sections


def extract_section(content: str, header: str) -> str | None:
    """Return the content of a named H2 section, or None if not found."""
    for sec in parse_sections(content):
        if sec.name.lower() == header.lower():
            return sec.content
    return None


def list_sections(content: str) -> list[dict]:
    """Return [{name, preview, is_empty}] for all H2 sections."""
    return [
        {"name": s.name, "preview": s.preview, "is_empty": s.is_empty}
        for s in parse_sections(content)
    ]


def sections_prompt_block(content: str) -> str:
    """Format sections as a numbered list for use in AI prompts."""
    sections = parse_sections(content)
    if not sections:
        return "(no sections found)"
    lines = []
    for i, s in enumerate(sections, 1):
        preview = f" — {s.preview}" if not s.is_empty else " (empty)"
        lines.append(f"{i}. {s.name}{preview}")
    return "\n".join(lines)


# ── content manipulation (returns new strings — never writes) ──────────────

def replace_section_content(note_content: str, section_name: str, new_body: str) -> str:
    """Return the note with a named section's body replaced.

    Preserves the ## header line and all surrounding content.
    Raises ValueError if the section is not found.
    """
    sections = parse_sections(note_content)
    target = next((s for s in sections if s.name.lower() == section_name.lower()), None)
    if target is None:
        raise ValueError(f"Section '{section_name}' not found in note.")

    lines = note_content.splitlines()
    header_line = lines[target.line_start]
    before = lines[:target.line_start]
    after  = lines[target.line_end:]

    body_lines = new_body.rstrip("\n").splitlines()
    assembled  = before + [header_line, ""] + body_lines + [""] + after

    return _clean_blank_lines("\n".join(assembled))


def insert_section_after(
    note_content: str,
    after_section: str,
    new_section_name: str,
    new_body: str,
) -> str:
    """Return the note with a new H2 section inserted after `after_section`.

    If `after_section` is not found, appends the new section at the end.
    """
    sections = parse_sections(note_content)
    target = next((s for s in sections if s.name.lower() == after_section.lower()), None)

    lines = note_content.splitlines()
    insert_at = target.line_end if target is not None else len(lines)

    new_block = ["", f"## {new_section_name}", ""] + new_body.rstrip("\n").splitlines() + [""]

    assembled = lines[:insert_at] + new_block + lines[insert_at:]
    return _clean_blank_lines("\n".join(assembled))


def _clean_blank_lines(text: str) -> str:
    """Collapse runs of 3+ blank lines to 2."""
    import re
    return re.sub(r"\n{3,}", "\n\n", text)
