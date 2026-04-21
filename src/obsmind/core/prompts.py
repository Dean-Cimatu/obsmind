"""Load and render prompt templates from the prompts/ directory."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load(name: str, **kwargs: str) -> str:
    """Load a prompt markdown file and substitute {key} placeholders.

    Args:
        name: Filename stem, e.g. 'daily_update' loads daily_update.md
        **kwargs: Template variables to substitute.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {path}\n"
            f"Fix: create src/obsmind/prompts/{name}.md"
        )
    template = path.read_text()
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise ValueError(
            f"Prompt '{name}' requires a template variable {e} that was not provided."
        ) from e
