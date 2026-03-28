import asyncio
import logging
import os

import db
from crawlers import arxiv, github, huggingface, news
from summarizer import summarize
from topics import tag_entry

logger = logging.getLogger(__name__)


def _twitter_enabled() -> bool:
    return os.getenv("TWITTER_ENABLED", "false").lower() == "true"


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
    """Fetch new items from all enabled sources concurrently, then process."""
    logger.info("Starting crawl cycle...")

    crawl_coros = [
        github.fetch_new(),
        arxiv.fetch_rss(),
        huggingface.fetch_new(),
        news.fetch_new(),
    ]

    if _twitter_enabled():
        from crawlers import twitter
        crawl_coros.append(twitter.fetch_new())

    results = await asyncio.gather(*crawl_coros, return_exceptions=True)

    all_items = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Crawl source error: %s", r)
        else:
            all_items.extend(r)

    logger.info("Crawl fetched %d items total", len(all_items))
    stored = await _process_items(all_items)
    logger.info("Crawl cycle complete: %d new items stored", stored)


async def run_backfill() -> None:
    """One-time historical backfill. GitHub + HuggingFace + arXiv (no Twitter — RSS has no history)."""
    logger.info("Starting historical backfill...")

    github_items = await github.backfill(since="2025-12-01")
    logger.info("GitHub backfill: %d items fetched", len(github_items))
    gh_stored = await _process_items(github_items)
    logger.info("GitHub backfill: %d new items stored", gh_stored)

    hf_items = await huggingface.fetch_new()
    logger.info("HuggingFace backfill: %d items fetched", len(hf_items))
    hf_stored = await _process_items(hf_items)
    logger.info("HuggingFace backfill: %d new items stored", hf_stored)

    logger.info("Starting arXiv backfill (this may take 30-90 minutes)...")
    arxiv_items = await arxiv.backfill(months=3)
    logger.info("arXiv backfill: %d items fetched", len(arxiv_items))
    ax_stored = await _process_items(arxiv_items)
    logger.info("arXiv backfill: %d new items stored", ax_stored)

    logger.info(
        "Backfill complete. Total stored: %d",
        gh_stored + hf_stored + ax_stored,
    )
