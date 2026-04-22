"""Claude API wrapper with strict model tiering and usage logging.

Every call goes through ai.call(task, ...). The task name maps to a model
tier in TIER_MAP — this is the single source of truth for cost control.
No per-call model overrides unless explicitly justified.
"""

import os
import time
from dataclasses import dataclass
from typing import Iterator

import anthropic

from .usage import log_usage

# ── model constants ────────────────────────────────────────────────────────

HAIKU  = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
OPUS   = "claude-opus-4-7"

# Per-token cost in USD (input, output)
_COST: dict[str, tuple[float, float]] = {
    HAIKU:  (0.80 / 1_000_000,  4.00 / 1_000_000),
    SONNET: (3.00 / 1_000_000, 15.00 / 1_000_000),
    OPUS:   (15.0 / 1_000_000, 75.00 / 1_000_000),
}

# ── tier map — one place, authoritative ───────────────────────────────────

TIER_MAP: dict[str, str] = {
    "ping":           HAIKU,   # doctor health check
    "context_build":  SONNET,  # context update (future stages)
    "daily_update":   SONNET,  # surgical daily note edits
    "daily_reflect":  SONNET,  # end-of-day reflection formatting
    "daily_fill":     SONNET,  # Focus Areas suggestions
    "daily_summary":  HAIKU,   # read-only day summary
    # note commands
    "note_edit":      SONNET,  # surgical section edit
    "note_extend":    SONNET,  # new section generation
    "note_enhance":   SONNET,  # fill incomplete sections
    "note_rewrite":   SONNET,  # section-level rewrite
    "note_rewrite_full": OPUS, # whole-note rewrite (--full)
    "note_fix":       HAIKU,   # structural fixes only (headings, frontmatter)
    "note_tags":      HAIKU,   # propose/update tags
    "note_summarise": HAIKU,   # read-only summary
    # ask / find
    "ask":            SONNET,  # RAG question answering (may auto-escalate to Opus)
    "ask_opus":       OPUS,    # analytical / high-source-count asks
    "find":           HAIKU,   # semantic ranking without generation
    # review / prioritise / generate
    "review":         OPUS,    # weekly review (full vault scan)
    "prioritise":     SONNET,  # rank open todos
    "generate":       OPUS,    # full note generation from scratch
    # other
    "qa":             SONNET,  # vault question answering
    "search":         HAIKU,   # semantic search scoring
}


def model_for(task: str) -> str:
    """Return the model ID for a named task."""
    if task not in TIER_MAP:
        raise ValueError(
            f"Unknown task '{task}'. "
            f"Add it to TIER_MAP in core/ai.py. "
            f"Known tasks: {', '.join(TIER_MAP)}"
        )
    return TIER_MAP[task]


def tier_name(model: str) -> str:
    names = {HAIKU: "haiku", SONNET: "sonnet", OPUS: "opus"}
    return names.get(model, model)


# ── response ───────────────────────────────────────────────────────────────

@dataclass
class AIResponse:
    content: str
    model: str
    task: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    elapsed_ms: int

    @property
    def tier(self) -> str:
        return tier_name(self.model)

    def meta_line(self) -> str:
        """Dim summary for display after a command."""
        return (
            f"{self.tier}  "
            f"{self.input_tokens}→{self.output_tokens} tok  "
            f"${self.cost_usd:.5f}  "
            f"{self.elapsed_ms}ms"
        )


# ── client ─────────────────────────────────────────────────────────────────

def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Fix: export ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic(api_key=api_key)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = _COST.get(model, (0.0, 0.0))
    return input_tokens * in_rate + output_tokens * out_rate


# ── public API ─────────────────────────────────────────────────────────────

def call(
    task: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
    command: str = "",
) -> AIResponse:
    """Call Claude for a named task. Logs usage automatically.

    Args:
        task: Key in TIER_MAP — determines the model used.
        prompt: User message.
        system: System prompt. If empty, uses a minimal default.
        max_tokens: Maximum output tokens.
        command: CLI command name for usage log (e.g. 'doctor').
    """
    model = model_for(task)
    client = _client()
    sys_prompt = system or "You are ObsMind, an AI assistant for an Obsidian vault."

    t0 = time.monotonic()
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=sys_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    input_tokens  = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    cost          = _estimate_cost(model, input_tokens, output_tokens)
    content       = message.content[0].text if message.content else ""

    log_usage(
        command=command or task,
        task=task,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )

    return AIResponse(
        content=content,
        model=model,
        task=task,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        elapsed_ms=elapsed_ms,
    )


def stream(
    task: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
    command: str = "",
) -> Iterator[str]:
    """Stream a Claude response token by token. Logs usage on completion.

    Yields text chunks. Caller is responsible for printing them.
    """
    model = model_for(task)
    client = _client()
    sys_prompt = system or "You are ObsMind, an AI assistant for an Obsidian vault."

    t0 = time.monotonic()
    input_tokens = output_tokens = 0

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=sys_prompt,
        messages=[{"role": "user", "content": prompt}],
    ) as s:
        for text in s.text_stream:
            yield text
        final = s.get_final_message()
        input_tokens  = final.usage.input_tokens
        output_tokens = final.usage.output_tokens

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    cost = _estimate_cost(model, input_tokens, output_tokens)

    log_usage(
        command=command or task,
        task=task,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )
