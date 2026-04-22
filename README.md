# ObsMind

AI companion CLI for your Obsidian vault, powered by Claude.

```
pip install obsmind
export ANTHROPIC_API_KEY=sk-ant-...
obsmind doctor
```

Requires [ObsFlow](https://github.com/Dean-Cimatu/obsflow) (`npm install -g obsflow`) for all write operations.

---

## Commands

### Daily note
```
obsmind daily --update "finished the auth module"   # route text to the right section
obsmind daily --reflect                              # interactive end-of-day reflection
obsmind daily --fill                                 # suggest Focus Areas from context
obsmind daily summary                                # structured summary of today
```

### Note editing
```
obsmind note edit "My Note" --section "Overview" --instruction "be more concise"
obsmind note extend "My Note" --section "References"
obsmind note enhance "My Note"                       # fill incomplete sections
obsmind note rewrite "My Note" --section "Goals" --instruction "rewrite as bullets"
obsmind note rewrite "My Note" --full --instruction "tighten the prose"
obsmind note fix "My Note"                           # structural fixes: headings, frontmatter, bullets
obsmind note tags "My Note" --apply                  # propose and write frontmatter tags
obsmind note summarise "My Note"
```

### Vault QA
```
obsmind ask "what did I decide about the auth architecture?"
obsmind ask "compare my project notes" --opus         # force Opus
obsmind find "machine learning"                       # rank notes by relevance
```

### Review & planning
```
obsmind review                                        # weekly review (last 7 days)
obsmind review --days 14
obsmind prioritise                                    # rank all open todos
```

### Note generation
```
obsmind generate "Project Alpha" --instruction "new software project, Python backend"
obsmind generate "Meeting Notes" --instruction "AWS architecture review" --folder "Meetings"
obsmind generate "Draft Title" --instruction "..." --dry-run
```

### Config & diagnostics
```
obsmind config set vault_path /path/to/vault
obsmind config set daily_notes_folder "Daily Notes"
obsmind config get
obsmind context update                                # cache vault context for prompts
obsmind profile set dev                               # dev | work | study
obsmind usage                                         # API cost summary
obsmind doctor                                        # verify full setup
obsmind --version
```

---

## Setup

### 1. Install
```
pip install obsmind
```

### 2. API key
```
export ANTHROPIC_API_KEY=sk-ant-...
```
Add to `~/.zshrc` or `~/.bash_profile` to persist.

### 3. Configure vault
```
obsmind config set vault_path /path/to/your/vault
```

### 4. Install ObsFlow (required for writes)
```
npm install -g obsflow
obs init
```

### 5. Verify
```
obsmind doctor
```

---

## Model tiers

ObsMind uses three Claude tiers based on task complexity:

| Tier | Model | Used for |
|------|-------|----------|
| Haiku | `claude-haiku-4-5` | Tags, fix, summarise, find |
| Sonnet | `claude-sonnet-4-6` | Daily edits, ask, prioritise, note edit/extend/enhance/rewrite |
| Opus | `claude-opus-4-7` | Note rewrite --full, ask (analytical), review, generate |

`obsmind ask` auto-escalates to Opus when the question contains analytical patterns (`compare`, `analyse`, `what patterns`, etc.) or when ≥9 sources are retrieved.

---

## Write safety

ObsMind never writes vault files directly. All writes go through `obs` (ObsFlow), which backs up the original to `.obsflow/trash/` before any change. Every destructive operation is reversible with `obs undo`.

---

## Usage tracking

All API calls are logged to `~/.obsmind/usage.jsonl`. View a summary:
```
obsmind usage
obsmind usage --month 2026-04
```

---

## Requirements

- Python ≥ 3.11
- [ObsFlow](https://github.com/Dean-Cimatu/obsflow) ≥ 1.0.0 (Node.js ≥ 18)
- `ANTHROPIC_API_KEY` environment variable
