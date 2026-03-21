# info_digger

AI industry intelligence system. Automatically crawls GitHub, arXiv, and HuggingFace for the latest AI developments, generates one-sentence summaries with Claude, aggregates everything on a timeline, and provides natural-language Q&A.

**Core belief: to see what's coming, you have to see what's happening.**

## Features

- **Multi-source crawling** — GitHub trending repos, arXiv papers (cs.AI / cs.LG / cs.CL), HuggingFace latest models, X/Twitter (optional, off by default)
- **Auto-summarization** — every entry gets a one-sentence summary from Claude Haiku
- **Topic tagging** — keyword-based auto-tagging (LLM Reasoning, RAG, Agents, Multimodal, etc.)
- **Timeline UI** — grouped by month, multi-source filtering, infinite scroll
- **Activity chart** — SVG line chart showing topic heat across platforms over time
- **Research assistant** — `POST /api/ask`: ask questions in plain English, answered with collected data
- **Health monitoring** — `GET /admin/health`: crawler status + Claude API success rate
- **Docker support** — one-command startup with persistent SQLite storage

## Quick Start

**Option 1: Bare install**

```bash
git clone https://github.com/TbearFC/info_digger
cd info_digger
pip install -r requirements.txt
cp .env.example .env      # fill in ANTHROPIC_API_KEY
uvicorn main:app --reload
```

**Option 2: Docker**

```bash
git clone https://github.com/TbearFC/info_digger
cd info_digger
cp .env.example .env      # fill in ANTHROPIC_API_KEY
docker-compose up
```

Open `http://localhost:8000`. On first run, 3 months of history is automatically backfilled (arXiv takes 30–90 min). After that, crawls run every hour.

## Configuration

Copy `.env.example` to `.env` and fill in as needed:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | — | Claude API key |
| `DB_PATH` | — | `./data/info_digger.db` | SQLite file path |
| `CLAUDE_MODEL` | — | `claude-haiku-4-5-20251001` | Model used for summaries and Q&A |
| `GITHUB_TOKEN` | — | — | Raises GitHub rate limit to 5,000 req/hr |
| `HF_API_TOKEN` | — | — | Raises HuggingFace rate limit |
| `TWITTER_ENABLED` | — | `false` | Set to `true` to enable the Twitter crawler |
| `NITTER_URL` | — | — | Required when Twitter is enabled (nitter.net is offline — needs a self-hosted instance) |
| `TWITTER_ACCOUNTS` | — | `karpathy,ylecun,sama` | Accounts to track (comma-separated) |
| `DB_BACKFILLED` | — | — | Set to `1` to skip the history backfill on next restart |

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/entries` | Fetch entries — supports `topic`, `source`, `limit`, `offset` filters |
| `GET /api/topics` | List all topic tags |
| `GET /api/stats` | Monthly entry counts per topic (activity chart data source) |
| `POST /api/ask` | Natural language Q&A — body: `{"question": "...", "topic": "..."}` |
| `GET /admin/health` | Crawler status + Claude API success rate |

## Tech Stack

Python · FastAPI · SQLite (WAL) · APScheduler · httpx · feedparser · Anthropic Claude API · native SVG · zero frontend dependencies
