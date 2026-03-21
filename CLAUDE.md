# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY
uvicorn main:app --reload
```

Open `http://localhost:8000`. The app runs a one-time historical backfill on first start (arXiv takes 30–90 min), then crawls every 60 minutes. A `.backfilled` sentinel file prevents repeat backfills on restart; set `DB_BACKFILLED=1` in `.env` to skip it.

## Architecture

The pipeline flows: **crawl → dedup → tag → summarize → store → serve**.

```
crawlers/github.py   crawlers/arxiv.py   (+ huggingface.py, twitter.py planned)
        └─────────────────┬──────────────────┘
                          ▼
                    pipeline.py          ← orchestrator (asyncio.gather for concurrent fetch)
                    hash_exists()        ← dedup via content_hash (SHA-256 of title+url)
                    tag_entry()          ← topics.py keyword match → list[str]
                    summarize()          ← summarizer.py → Claude Haiku 1-sentence
                    insert_entry()       ← db.py SQLite
                          ▼
                    FastAPI (main.py)
                    GET /api/entries     ← filtered by topic, source, offset
                    GET /api/topics      ← distinct tags from DB
                    GET /               ← static/index.html (vanilla JS timeline)
```

**Key design decisions:**
- SQLite with `PRAGMA journal_mode=WAL` — safe concurrent reads (FastAPI) + writes (pipeline)
- `content_hash = sha256(title + url)` — idempotent dedup; crawlers can re-run safely
- Topic tagging is keyword-based (no LLM) — `topics.py` defines `TOPICS` dict; `tag_entry()` returns matching topic names; entries with zero tags are **dropped** (out of scope for MVP)
- Summarizer returns `""` on any Claude API error — never blocks ingestion
- Backfill runs once via sentinel file `.backfilled`; scheduler (`APScheduler`) runs `run_crawl()` hourly

## Environment variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API |
| `DB_PATH` | No | `./data/info_digger.db` | SQLite file path |
| `GITHUB_TOKEN` | No | — | Raises GitHub rate limit to 5000/hr |
| `DB_BACKFILLED` | No | — | Set to `1` to skip backfill on restart |
| `CLAUDE_MODEL` | No | `claude-haiku-4-5-20251001` | Model for summarizer + /api/ask |

## Adding a new crawler

1. Create `crawlers/<source>.py` with `async def fetch_new() -> list[dict]` and optionally `async def backfill() -> list[dict]`
2. Each dict must have: `source`, `url`, `title`, `description`, `published_at` (ISO8601 naive UTC), `content_hash`
3. Add calls to `run_crawl()` and `run_backfill()` in `pipeline.py`
4. Add source button + CSS vars to `static/index.html`

## gstack

This project includes gstack at `.claude/skills/gstack/`. Use it for all web browsing and QA workflows.

**Web browsing:** Always use the `/browse` skill (`$B` binary at `.claude/skills/gstack/browse/dist/browse`). Never use `mcp__claude-in-chrome__*` tools — they are slow and unreliable.

**Available skills:**
`/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/review`, `/ship`, `/browse`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`

**If skills aren't working:** run `cd .claude/skills/gstack && ./setup` to build the binary and register skills.
