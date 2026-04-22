# Changelog

## [1.0.0] — 2026-04-22

### Added

**Stage 1 — Foundation**
- Typer CLI scaffold with `--version`, `doctor`, `usage` commands
- Claude API wrapper with model tiering (Haiku / Sonnet / Opus) in a single `TIER_MAP`
- Usage logging to `~/.obsmind/usage.jsonl` with per-call cost estimation
- Vault bridge — reads notes and frontmatter, never writes directly
- Context system — cache vault summary for prompt injection
- Profile system — switch between `dev`, `work`, `study` modes

**Stage 2 — Daily note surgical edits**
- `obsmind daily --update` — AI routes text to the correct daily note section
- `obsmind daily --reflect` — interactive end-of-day reflection with formatting
- `obsmind daily --fill` — suggest Focus Areas from recent context
- `obsmind daily summary` — structured read-only summary

**Stage 3 — Note editing**
- `obsmind note edit` — surgical section replacement
- `obsmind note extend` — insert new section with AI-generated content
- `obsmind note enhance` — fill incomplete sections without removing content
- `obsmind note rewrite` — rewrite section (Sonnet) or full note (Opus)
- `obsmind note fix` — structural fixes: heading hierarchy, frontmatter schema, bullet normalisation
- `obsmind note tags` — propose and apply frontmatter tags
- `obsmind note summarise` — read-only structured summary panel

**Stage 4 — Vault QA**
- `obsmind ask` — RAG question answering with `[[citation]]` inline refs
- Auto-escalation to Opus for analytical queries or large source sets
- `obsmind find` — keyword + link-neighbourhood retrieval with Claude re-ranking

**Stage 5 — Review & planning**
- `obsmind review` — streamed weekly review from daily notes and projects
- `obsmind prioritise` — rank all open vault todos by urgency and importance

**Stage 6 — Note generation**
- `obsmind generate` — create new vault notes from scratch using Opus
- `--folder` flag for subfolder placement
- `--dry-run` for preview without writing
- Related-note context injection via retrieval

**Stage 7 — Release**
- PyPI package at `pip install obsmind`
- GitHub Actions workflow: test → publish on `v*.*.*` tag
- Self-update check (24h cache, silent on failure)
