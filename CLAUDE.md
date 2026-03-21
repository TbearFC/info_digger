# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Vision

**info_digger** is an AI industry intelligence system that:
1. Crawls and ingests the latest AI-related content from X (Twitter), GitHub, HuggingFace, arXiv, and other AI platforms
2. Analyzes and summarizes ingested content using LLMs
3. Exposes an interactive interface (chat/query) for users to explore findings

The system prioritizes **recency and speed** — getting the newest information as fast as possible.

## Architecture (Planned)

The system is being designed. When implementing, follow this intended layered architecture:

```
Collectors (per-source scrapers/API clients)
    ↓
Ingestion Queue (dedup, normalize, timestamp)
    ↓
Storage (raw + processed)
    ↓
Analysis Pipeline (summarize, tag, rank by relevance)
    ↓
Interactive Interface (chat UI or CLI)
```

**Key data sources to support:**
- X/Twitter — trending AI discussions, paper drops, model releases
- GitHub — trending repos, new releases in AI orgs
- HuggingFace — new models, datasets, spaces
- arXiv — cs.AI, cs.LG, cs.CL paper feeds

## Technology Decisions

No stack has been locked in yet. When proposing or implementing:
- Prefer Python for backend/pipeline work (ecosystem fit for AI tooling)
- Use async patterns (asyncio / httpx) for concurrent multi-source crawling
- Storage: consider SQLite for local dev, PostgreSQL for prod; vector store (e.g., ChromaDB or pgvector) for semantic search
- LLM calls: use the Anthropic Claude API (claude-sonnet-4-6 or claude-haiku-4-5) for summarization and analysis
- Interactive layer: start with a CLI REPL, plan for a web UI (FastAPI + minimal frontend)

## What to Build Next

The project is in early ideation. Suggested first steps:
1. Define data schemas (source, content, timestamp, embeddings, tags)
2. Build one collector end-to-end (GitHub trending is simplest — public API, no auth needed)
3. Wire up a basic analysis pipeline (chunk → summarize → store)
4. Add a simple query interface

## Conventions

- All collectors should implement a common interface (e.g., `async def fetch() -> list[RawItem]`)
- Raw data must always be stored before processing (preserve originals)
- Every ingested item needs: `source`, `url`, `fetched_at`, `content_hash` (for dedup)
