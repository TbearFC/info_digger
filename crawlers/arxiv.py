import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta

import feedparser
import httpx
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

_RSS_FEEDS = [
    "https://export.arxiv.org/rss/cs.AI",
    "https://export.arxiv.org/rss/cs.LG",
    "https://export.arxiv.org/rss/cs.CL",
]

_SEARCH_BASE = "https://export.arxiv.org/search/"


def _canonical_url(url: str) -> str:
    """Strip version suffix (v1, v2...) from arXiv URL for stable dedup."""
    return re.sub(r"v\d+$", "", url.rstrip("/"))


def _parse_feed_entry(entry) -> dict:
    url = _canonical_url(getattr(entry, "link", "") or "")
    title = getattr(entry, "title", "").replace("\n", " ").strip()
    summary = getattr(entry, "summary", "") or ""
    # feedparser stores date in 'published' or 'updated'
    published = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if published:
        try:
            published_at = datetime(*published[:6]).isoformat()
        except Exception:
            published_at = datetime.utcnow().isoformat()
    else:
        published_at = datetime.utcnow().isoformat()

    content_hash = hashlib.sha256((title + url).encode()).hexdigest()
    return {
        "source": "arxiv",
        "url": url,
        "title": title,
        "description": summary[:500],
        "published_at": published_at,
        "content_hash": content_hash,
    }


async def fetch_rss() -> list[dict]:
    """Fetch latest entries from arXiv RSS feeds (cs.AI, cs.LG, cs.CL)."""
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for feed_url in _RSS_FEEDS:
            try:
                resp = await client.get(feed_url)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
                for entry in feed.entries:
                    results.append(_parse_feed_entry(entry))
                logger.info("arXiv RSS %s: %d entries", feed_url, len(feed.entries))
            except Exception as exc:
                logger.warning("arXiv RSS %s failed: %s", feed_url, exc)
    return results


async def backfill(months: int = 3) -> list[dict]:
    """
    Backfill using arXiv Search API (Atom/XML).
    Respects 3s delay between requests per arXiv ToS.
    Max 10 pages × 100 results = 1000 entries per category.
    """
    since = datetime.utcnow() - timedelta(days=months * 30)
    since_str = since.strftime("%Y%m%d")
    results: list[dict] = []

    for category in ["cs.AI", "cs.LG", "cs.CL"]:
        logger.info("arXiv backfill starting for %s since %s", category, since_str)
        for page in range(10):
            start = page * 100
            params = {
                "searchtype": "cat",
                "query": category,
                "start": str(start),
                "max_results": "100",
                "order": "-announced_date_first",
            }
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.get(_SEARCH_BASE, params=params)
                    resp.raise_for_status()

                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entries = root.findall("atom:entry", ns)

                if not entries:
                    break

                page_results = []
                stop = False
                for entry in entries:
                    published_el = entry.find("atom:published", ns)
                    published_str = published_el.text if published_el is not None else ""
                    try:
                        published_dt = datetime.fromisoformat(
                            published_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except Exception:
                        published_dt = datetime.utcnow()

                    if published_dt < since:
                        stop = True
                        break

                    id_el = entry.find("atom:id", ns)
                    title_el = entry.find("atom:title", ns)
                    summary_el = entry.find("atom:summary", ns)

                    url = _canonical_url(id_el.text.strip() if id_el is not None else "")
                    title = (title_el.text or "").replace("\n", " ").strip()
                    description = (summary_el.text or "").replace("\n", " ").strip()[:500]
                    content_hash = hashlib.sha256((title + url).encode()).hexdigest()

                    page_results.append({
                        "source": "arxiv",
                        "url": url,
                        "title": title,
                        "description": description,
                        "published_at": published_dt.isoformat(),
                        "content_hash": content_hash,
                    })

                results.extend(page_results)
                logger.info(
                    "arXiv backfill %s page %d: %d entries", category, page, len(page_results)
                )

                if stop or len(entries) < 100:
                    break

                await asyncio.sleep(3)  # respect arXiv ToS

            except Exception as exc:
                logger.warning("arXiv backfill %s page %d failed: %s", category, page, exc)
                break

        await asyncio.sleep(3)  # between categories

    return results
