from abc import ABC, abstractmethod
from typing import Any


class Profile(ABC):
    """Abstract base for ObsMind user profiles.

    A profile customises the system prompt, note templates, and command
    behaviour for a specific user or context. Subclass this to add a new
    profile — see profiles/README.md for instructions.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. 'dev' or 'writer'."""
        ...

    @abstractmethod
    def system_prompt_addition(self) -> str:
        """Extra context appended to every system prompt.

        Use this to describe the user's role, goals, and working style so
        Claude can tailor its responses appropriately.
        """
        ...

    @abstractmethod
    def note_templates(self) -> dict[str, str]:
        """Map of template name → markdown template string.

        Templates can reference {{placeholders}} expanded at generation time.
        """
        ...

    @abstractmethod
    def command_overrides(self) -> dict[str, Any]:
        """Map of command name → override dict.

        Example: {'daily_update': {'model_tier': 'sonnet'}} would force the
        daily_update command to use Sonnet even if the default is Haiku.
        """
        ...
