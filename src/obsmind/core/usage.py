"""Append-only usage log at ~/.obsmind/usage.jsonl.

One JSON line per API call: timestamp, command, model, tokens, cost.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

USAGE_DIR  = Path.home() / ".obsmind"
USAGE_FILE = USAGE_DIR / "usage.jsonl"


def log_usage(
    command: str,
    task: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    """Append one usage record. Silently ignores write errors."""
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts":            datetime.now(timezone.utc).isoformat(),
        "command":       command,
        "task":          task,
        "model":         model,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "cost_usd":      cost_usd,
    }
    try:
        with USAGE_FILE.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass


def read_usage(month: str | None = None) -> list[dict]:
    """Read all usage records, optionally filtered to a YYYY-MM month string."""
    if not USAGE_FILE.exists():
        return []
    records = []
    with USAGE_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if month and not rec.get("ts", "").startswith(month):
                    continue
                records.append(rec)
            except json.JSONDecodeError:
                continue
    return records


def summarise_usage(records: list[dict]) -> dict:
    """Aggregate usage records into totals."""
    total_calls    = len(records)
    total_input    = sum(r.get("input_tokens",  0) for r in records)
    total_output   = sum(r.get("output_tokens", 0) for r in records)
    total_cost     = sum(r.get("cost_usd",      0.0) for r in records)

    by_model: dict[str, dict] = {}
    for r in records:
        m = r.get("model", "unknown")
        if m not in by_model:
            by_model[m] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        by_model[m]["calls"]         += 1
        by_model[m]["input_tokens"]  += r.get("input_tokens",  0)
        by_model[m]["output_tokens"] += r.get("output_tokens", 0)
        by_model[m]["cost_usd"]      += r.get("cost_usd",      0.0)

    return {
        "total_calls":    total_calls,
        "total_input":    total_input,
        "total_output":   total_output,
        "total_cost_usd": total_cost,
        "by_model":       by_model,
    }
