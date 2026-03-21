# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY
uvicorn main:app --reload
```

Or with Docker:
```bash
docker-compose up
```

Open `http://localhost:8000`. On first start, a one-time historical backfill runs (arXiv takes 30–90 min), then crawls every 60 minutes. A `.backfilled` sentinel file prevents repeat backfills; set `DB_BACKFILLED=1` in `.env` to skip it permanently.

## Architecture

The pipeline flows: **crawl → dedup → tag → summarize → store → serve**.

```
crawlers/github.py   crawlers/arxiv.py   crawlers/huggingface.py   crawlers/twitter.py*
        └──────────────────────┬──────────────────────────────────┘
                               ▼
                         pipeline.py          ← orchestrator; asyncio.gather for concurrent fetch
                         hash_exists()        ← dedup via content_hash (SHA-256)
                         tag_entry()          ← topics.py keyword match → list[str]
                         summarize()          ← summarizer.py → Claude API 1-sentence
                         insert_entry()       ← db.py SQLite (WAL mode)
                               ▼
                         FastAPI (main.py)
                         GET  /api/entries    ← filtered by topic, source, offset
                         GET  /api/topics     ← distinct tags from DB
                         GET  /api/stats      ← monthly counts per source (for SVG chart)
                         POST /api/ask        ← research assistant (Claude API, non-streaming)
                         GET  /admin/health   ← crawler status + Claude API success rate
                         GET  /              ← static/index.html (vanilla JS)
```

*Twitter/Nitter is disabled by default (`TWITTER_ENABLED=false`). Also excluded from `run_backfill()` — RSS has no history.

**Key design decisions:**
- SQLite WAL mode — safe concurrent reads (FastAPI) + writes (pipeline); no extra locking needed at MVP scale
- `content_hash`: GitHub/arXiv/Twitter = `sha256(title + url)`; HuggingFace = `sha256(modelId)` — crawlers are idempotent
- Topic tagging is keyword-based (no LLM) — `topics.py::TOPICS` dict; entries with zero tags are **dropped**
- `summarizer.py` and `POST /api/ask` both read model from `CLAUDE_MODEL` env var; all Claude API calls write to `api_calls` table for health monitoring
- Summarizer returns `""` on error — never blocks ingestion

## Environment variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `DB_PATH` | No | `./data/info_digger.db` | SQLite path; `db.init()` auto-creates parent dir |
| `CLAUDE_MODEL` | No | `claude-haiku-4-5-20251001` | Used by summarizer + `/api/ask` |
| `GITHUB_TOKEN` | No | — | Raises rate limit from 60 → 5000 req/hr |
| `DB_BACKFILLED` | No | — | Set to `1` to skip backfill on restart |
| `HF_API_TOKEN` | No | — | Raises HuggingFace rate limit |
| `TWITTER_ENABLED` | No | `false` | Set to `true` to enable Nitter crawler |
| `NITTER_URL` | No | — | Required when Twitter enabled; nitter.net is offline — supply your own instance |
| `TWITTER_ACCOUNTS` | No | `karpathy,ylecun,sama` | Comma-separated accounts to track |

## Database schema

Two tables, both created in `db.init()`:

- **`entries`** — all ingested items. Key fields: `source`, `url`, `title`, `summary`, `topic_tags` (JSON array), `published_at` (ISO8601 naive UTC), `content_hash` (UNIQUE)
- **`api_calls`** — Claude API call log for health monitoring. Fields: `called_at`, `caller` (`"summarizer"` or `"ask"`), `success` (0/1), `error_msg`

## Adding a new crawler

1. Create `crawlers/<source>.py` with `async def fetch_new() -> list[dict]`; optionally `async def backfill() -> list[dict]`
2. Each dict must have: `source`, `url`, `title`, `description`, `published_at` (ISO8601 naive UTC), `content_hash`
3. Wire into `run_crawl()` and `run_backfill()` in `pipeline.py`
4. Add source button + CSS color vars to `static/index.html`

## gstack

This project includes gstack at `.claude/skills/gstack/`. Use it for all web browsing and QA workflows.

**Web browsing:** Always use the `/browse` skill (`$B` binary at `.claude/skills/gstack/browse/dist/browse`). Never use `mcp__claude-in-chrome__*` tools — they are slow and unreliable.

**Available skills:**
`/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/review`, `/ship`, `/browse`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`

**If skills aren't working:** run `cd .claude/skills/gstack && ./setup` to build the binary and register skills.
