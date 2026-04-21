# Adding a new ObsMind profile

A profile customises ObsMind's behaviour for a specific user or context — the
system prompt it sends to Claude, the note templates it generates, and any
per-command overrides.

## Steps

1. **Create the profile class**

   Copy `dev.py` to a new file, e.g. `writer.py`. Change the class name and
   implement all three abstract methods:

   ```python
   # src/obsmind/core/profiles/writer.py
   from typing import Any
   from .base import Profile

   class WriterProfile(Profile):
       @property
       def name(self) -> str:
           return "writer"

       def system_prompt_addition(self) -> str:
           return "You are assisting a fiction writer..."

       def note_templates(self) -> dict[str, str]:
           return {"chapter": "# {{title}}\n\n## Draft\n"}

       def command_overrides(self) -> dict[str, Any]:
           return {}
   ```

2. **Register it in `__init__.py`**

   Add an import and entry to the `PROFILES` dict:

   ```python
   from .writer import WriterProfile

   PROFILES: dict[str, type[Profile]] = {
       "dev": DevProfile,
       "writer": WriterProfile,   # ← add this
   }
   ```

3. **Switch to it**

   ```
   obsmind profile set writer
   ```

## What each method controls

| Method | Effect |
|--------|--------|
| `system_prompt_addition()` | Appended to every system prompt sent to Claude |
| `note_templates()` | Templates available to `obsmind generate` |
| `command_overrides()` | Per-command config overrides (e.g. force a model tier) |
