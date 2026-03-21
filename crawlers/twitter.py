import hashlib
import logging
import os
from datetime import datetime

import feedparser
import httpx

logger = logging.getLogger(__name__)


async def fetch_new() -> list[dict]:
    """Fetch tweets via Nitter RSS. Requires TWITTER_ENABLED=true and NITTER_URL set."""
    nitter_url = os.getenv("NITTER_URL", "").rstrip("/")
    accounts_str = os.getenv("TWITTER_ACCOUNTS", "karpathy,ylecun,sama")
    accounts = [a.strip() for a in accounts_str.split(",") if a.strip()]

    if not nitter_url:
        logger.warning("Twitter crawler enabled but NITTER_URL is not set — skipping")
        return []

    results = []
    for account in accounts:
        feed_url = f"{nitter_url}/{account}/rss"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(feed_url)
                resp.raise_for_status()
            feed = feedparser.parse(resp.text)
            for entry in feed.entries:
                url = getattr(entry, "link", "")
                title = getattr(entry, "title", "").strip()
                description = (getattr(entry, "summary", "") or "")[:500]
                published_parsed = getattr(entry, "published_parsed", None)
                if published_parsed:
                    try:
                        published_at = datetime(*published_parsed[:6]).isoformat()
                    except Exception:
                        published_at = datetime.utcnow().isoformat()
                else:
                    published_at = datetime.utcnow().isoformat()

                content_hash = hashlib.sha256((title + url).encode()).hexdigest()
                results.append({
                    "source": "twitter",
                    "url": url,
                    "title": title,
                    "description": description,
                    "published_at": published_at,
                    "content_hash": content_hash,
                })
            logger.info("Twitter @%s: %d entries", account, len(feed.entries))
        except Exception as exc:
            logger.warning("Twitter @%s failed: %s", account, exc)

    return results
