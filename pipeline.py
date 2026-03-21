import asyncio
import logging

import db
from crawlers import arxiv, github
from summarizer import summarize
from topics import tag_entry

logger = logging.getLogger(__name__)


async def _process_items(items: list[dict]) -> int:
    """Dedup → tag → summarize → store. Returns count of new items stored."""
    stored = 0
    for item in items:
        if db.hash_exists(item["content_hash"]):
            continue

        tags = tag_entry(item["title"], item.get("description", ""))
        if not tags:
            continue  # out of scope for MVP

        summary = await summarize(item["title"], item.get("description", ""))

        db.insert_entry(
            source=item["source"],
            url=item["url"],
            title=item["title"],
            summary=summary,
            topic_tags=tags,
            published_at=item["published_at"],
            content_hash=item["content_hash"],
        )
        stored += 1

    return stored


async def run_crawl() -> None:
    """Fetch new items from GitHub + arXiv RSS concurrently, then process."""
    logger.info("Starting crawl cycle...")
    github_items, arxiv_items = await asyncio.gather(
        github.fetch_new(),
        arxiv.fetch_rss(),
    )
    all_items = github_items + arxiv_items
    logger.info("Crawl fetched %d items total", len(all_items))
    stored = await _process_items(all_items)
    logger.info("Crawl cycle complete: %d new items stored", stored)


async def run_backfill() -> None:
    """One-time historical backfill. GitHub first (fast), then arXiv (slow)."""
    logger.info("Starting historical backfill...")

    github_items = await github.backfill(since="2025-12-01")
    logger.info("GitHub backfill: %d items fetched", len(github_items))
    gh_stored = await _process_items(github_items)
    logger.info("GitHub backfill: %d new items stored", gh_stored)

    logger.info("Starting arXiv backfill (this may take 30-90 minutes)...")
    arxiv_items = await arxiv.backfill(months=3)
    logger.info("arXiv backfill: %d items fetched", len(arxiv_items))
    ax_stored = await _process_items(arxiv_items)
    logger.info("arXiv backfill: %d new items stored", ax_stored)

    logger.info("Backfill complete. Total stored: %d", gh_stored + ax_stored)
