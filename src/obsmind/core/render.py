"""Note rendering — Rich for simple notes, Glow for complex/long ones.

Auto-selects based on content complexity. Falls back to Rich if Glow
is not installed.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

INDIGO = "bright_blue"

# ── thresholds ─────────────────────────────────────────────────────────────

_CHAR_THRESHOLD   = 1500   # chars — above this, prefer glow
_LINE_THRESHOLD   = 50     # lines — above this, prefer glow
_SECTION_THRESHOLD = 4     # H2 sections — above this, prefer glow


def _complexity(content: str) -> dict:
    """Score the rendering complexity of a note."""
    lines    = content.splitlines()
    chars    = len(content)
    sections = len(re.findall(r"^## ", content, re.MULTILINE))
    has_code = bool(re.search(r"^```", content, re.MULTILINE))
    has_table = bool(re.search(r"^\|", content, re.MULTILINE))
    return {
        "chars":     chars,
        "lines":     len(lines),
        "sections":  sections,
        "has_code":  has_code,
        "has_table": has_table,
    }


def _should_use_glow(content: str) -> bool:
    c = _complexity(content)
    return (
        c["chars"]    >= _CHAR_THRESHOLD  or
        c["lines"]    >= _LINE_THRESHOLD  or
        c["sections"] >= _SECTION_THRESHOLD or
        c["has_code"] or
        c["has_table"]
    )


def glow_available() -> bool:
    return shutil.which("glow") is not None


# ── renderers ──────────────────────────────────────────────────────────────

def render_rich(content: str, title: str = "") -> None:
    """Render note content using Rich Markdown inside a panel."""
    body = _strip_frontmatter(content)
    md   = Markdown(body, hyperlinks=True)
    if title:
        console.print(Panel(md, title=f"[{INDIGO}]{title}[/{INDIGO}]", border_style=INDIGO))
    else:
        console.print(md)


def render_glow(content: str, title: str = "") -> None:
    """Render note content using Glow. Falls back to Rich if glow unavailable."""
    if not glow_available():
        console.print(f"[dim](glow not installed — using Rich)[/dim]\n")
        render_rich(content, title)
        return

    body = _strip_frontmatter(content)

    # Write to a temp file so glow can page it properly
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        if title:
            f.write(f"# {title}\n\n")
        f.write(body)
        tmp_path = f.name

    try:
        subprocess.run(["glow", tmp_path], check=False)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def render(content: str, title: str = "", *, force: str = "") -> None:
    """Auto-select renderer based on content complexity.

    Args:
        content: Full note content (frontmatter included or not).
        title:   Display title for the panel/header.
        force:   "rich" or "glow" to override auto-selection.
    """
    use_glow = force == "glow" or (force != "rich" and _should_use_glow(content))

    if use_glow:
        render_glow(content, title)
    else:
        render_rich(content, title)


# ── helper ─────────────────────────────────────────────────────────────────

def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter block from note content."""
    return re.sub(r"^---\n.*?\n---\n?", "", content, flags=re.DOTALL).strip()
