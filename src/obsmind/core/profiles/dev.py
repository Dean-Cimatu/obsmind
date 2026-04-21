from typing import Any
from .base import Profile


class DevProfile(Profile):
    """Dean's developer profile.

    Optimised for a CS student / software engineer working across multiple
    projects (ObsFlow, ObsMind, Formula Student AI, academic work, placements).
    """

    @property
    def name(self) -> str:
        return "dev"

    def system_prompt_addition(self) -> str:
        return (
            "You are assisting Dean, a Computer Science student and software engineer. "
            "He works across multiple concurrent projects: personal tooling (ObsFlow, ObsMind), "
            "Formula Student AI (autonomous vehicle software), academic coursework, "
            "and an active placement search. "
            "His notes use Obsidian wikilinks extensively. "
            "When referencing a note or project, always use [[wikilink]] syntax. "
            "Be concise and technical. Prefer code and structured output over prose. "
            "Never add fluff, padding, or excessive caveats."
        )

    def note_templates(self) -> dict[str, str]:
        return {
            "project": (
                "---\n"
                "tags:\n"
                "  - project\n"
                "status: active\n"
                "started: {{date}}\n"
                "---\n"
                "# {{title}}\n\n"
                "## Overview\n\n"
                "## Goals\n\n"
                "## Links\n"
            ),
            "meeting": (
                "---\n"
                "tags:\n"
                "  - meeting\n"
                "date: {{date}}\n"
                "project: [[{{project}}]]\n"
                "---\n"
                "# {{title}}\n\n"
                "## Attendees\n\n"
                "## Notes\n\n"
                "## Actions\n"
            ),
        }

    def command_overrides(self) -> dict[str, Any]:
        return {}
