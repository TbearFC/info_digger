"""RSS/Atom crawler for AI company and industry news blogs."""
import hashlib
import logging
from datetime import datetime

import feedparser
import httpx

logger = logging.getLogger(__name__)

# (label, feed_url) — all treated as source="news"
_FEEDS = [
    ("OpenAI",             "https://openai.com/blog/rss.xml"),
    ("NVIDIA AI",          "https://blogs.nvidia.com/feed/"),
    ("Google Research",    "https://blog.research.google/atom.xml"),
    ("Google DeepMind",    "https://deepmind.google/blog/rss/"),
    ("Meta AI",            "https://engineering.fb.com/category/ai-research/feed/"),
    ("Anthropic",          "https://www.anthropic.com/rss.xml"),
    ("HuggingFace Blog",   "https://huggingface.co/blog/feed.xml"),
    ("The Batch",          "https://www.deeplearning.ai/the-batch/feed/"),
    ("VentureBeat AI",     "https://venturebeat.com/category/ai/feed/"),
    ("MIT Tech Review",    "https://www.technologyreview.com/feed/"),
]


def _parse_entry(entry, label: str) -> dict:
    url = getattr(entry, "link", "") or ""
    title = getattr(entry, "title", "").replace("\n", " ").strip()
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""

    published = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if published:
        try:
            published_at = datetime(*published[:6]).isoformat()
        except Exception:
            published_at = datetime.utcnow().isoformat()
    else:
        published_at = datetime.utcnow().isoformat()

    # Prepend source label to description so topic tagging has more signal
    description = f"[{label}] {summary[:400]}"
    content_hash = hashlib.sha256((title + url).encode()).hexdigest()

    return {
        "source": "news",
        "url": url,
        "title": title,
        "description": description,
        "published_at": published_at,
        "content_hash": content_hash,
    }


async def fetch_new() -> list[dict]:
    """Fetch latest entries from AI news RSS/Atom feeds."""
    results: list[dict] = []

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for label, feed_url in _FEEDS:
            try:
                resp = await client.get(feed_url)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
                count = 0
                for entry in feed.entries[:20]:  # cap at 20 per feed
                    item = _parse_entry(entry, label)
                    if item["url"] and item["title"]:
                        results.append(item)
                        count += 1
                logger.info("News RSS %s (%s): %d entries", label, feed_url, count)
            except Exception as exc:
                logger.warning("News RSS %s failed: %s", label, exc)

    return results
