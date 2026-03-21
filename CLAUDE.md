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

Open `http://localhost:8000`. On first start, a one-time historical backfill runs (arXiv takes 30–90 min), then crawls every 60 minutes. A `.backfilled` sentinel file prevents repeat backfills; set `DB_BACKFILLED=1` in `.env` to skip permanently.

## Architecture

Pipeline: **crawl → dedup → tag → summarize → store → serve**

```
crawlers/
  github.py        fetch_new() + backfill()   GitHub Search API
  arxiv.py         fetch_rss() + backfill()   arXiv RSS + Search API (3s delay, ToS)
  huggingface.py   fetch_new()                HF Models API (100 latest)
  twitter.py       fetch_new()                Nitter RSS — disabled by default

          └──────────────────┬───────────────────┘
                             ▼
                       pipeline.py
                         run_crawl()      asyncio.gather all enabled sources
                         run_backfill()   GitHub + HuggingFace + arXiv only (no Twitter)
                         _process_items() dedup → tag → summarize → insert
                             ▼
             ┌───────────────┼────────────────┐
          topics.py      summarizer.py      db.py
          tag_entry()    summarize()        SQLite WAL
          keyword match  Claude API         entries + api_calls tables
          → list[str]    max_tokens=100     log_api_call()
          zero tags      returns "" on err
          → item dropped
                             ▼
                       main.py  (FastAPI)
                         GET  /api/entries     topic + source + offset filter
                         GET  /api/topics      distinct tags
                         GET  /api/stats       monthly counts per source (SVG chart)
                         POST /api/ask         NL research assistant, max_tokens=500
                         GET  /admin/health    crawler status + Claude API success rate
                         GET  /               static/index.html
```

**Key design decisions:**
- SQLite WAL mode — concurrent reads (FastAPI) + writes (pipeline) with no extra locking at MVP scale
- `content_hash`: GitHub/arXiv/Twitter = `sha256(title+url)`; HuggingFace = `sha256(modelId)` — all crawls are idempotent
- Topic tagging is keyword-based (no LLM) — zero-tag items are **silently dropped**
- `summarizer.py` and `/api/ask` both use `CLAUDE_MODEL` env var; every Claude call writes to `api_calls` table
- Twitter excluded from `run_backfill()` — Nitter RSS has no history; `TWITTER_ENABLED=false` by default
- `/api/ask` injects up to 50 context entries (300 chars each); drops to 30 if estimated token count > 7000

## Environment variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `DB_PATH` | No | `./data/info_digger.db` | `db.init()` auto-creates parent dir |
| `CLAUDE_MODEL` | No | `claude-haiku-4-5-20251001` | Summarizer + `/api/ask` |
| `GITHUB_TOKEN` | No | — | Rate limit 60 → 5000 req/hr |
| `DB_BACKFILLED` | No | — | Set `1` to skip backfill on restart |
| `HF_API_TOKEN` | No | — | Raises HuggingFace rate limit |
| `TWITTER_ENABLED` | No | `false` | Set `true` to enable Nitter crawler |
| `NITTER_URL` | No | — | Required when Twitter enabled; nitter.net is offline |
| `TWITTER_ACCOUNTS` | No | `karpathy,ylecun,sama` | Comma-separated accounts |

## Database schema

Both tables created in `db.init()` via `CREATE TABLE IF NOT EXISTS` — safe for upgrades.

- **`entries`** — `source`, `url`, `title`, `summary`, `topic_tags` (JSON array), `published_at` (ISO8601 naive UTC), `content_hash` (UNIQUE), `fetched_at`
- **`api_calls`** — `called_at`, `caller` (`"summarizer"` | `"ask"`), `success` (0/1), `error_msg`

## Adding a new crawler

1. Create `crawlers/<source>.py` with `async def fetch_new() -> list[dict]`; optionally `async def backfill() -> list[dict]`
2. Each dict must have: `source`, `url`, `title`, `description`, `published_at` (ISO8601 naive UTC), `content_hash`
3. Wire into `run_crawl()` and (if backfill supported) `run_backfill()` in `pipeline.py`
4. Add source button + CSS color var to `static/index.html`

## gstack

This project includes gstack at `.claude/skills/gstack/`. Use it for all web browsing and QA workflows.

**Web browsing:** Always use the `/browse` skill (`$B` binary at `.claude/skills/gstack/browse/dist/browse`). Never use `mcp__claude-in-chrome__*` tools — they are slow and unreliable.

**Available skills:**
`/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/review`, `/ship`, `/browse`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`

**If skills aren't working:** run `cd .claude/skills/gstack && ./setup` to build the binary and register skills.
