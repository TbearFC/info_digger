import hashlib
import logging
import os
from datetime import datetime
from typing import Optional

import httpx

from topics import TOPICS

logger = logging.getLogger(__name__)

_BASE = "https://api.github.com/search/repositories"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _headers() -> dict:
    h = dict(_HEADERS)
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _all_keywords() -> str:
    """Build a combined OR query from all topic keywords."""
    kws: set[str] = set()
    for words in TOPICS.values():
        kws.update(words)
    # GitHub search: space = OR between terms; quote multi-word phrases
    parts = []
    for kw in sorted(kws):
        if " " in kw:
            parts.append(f'"{kw}"')
        else:
            parts.append(kw)
    return " ".join(parts[:50])  # GitHub limits query length


def _parse_item(item: dict) -> dict:
    title = item.get("full_name", "")
    url = item.get("html_url", "")
    description = item.get("description") or ""
    updated_at = item.get("updated_at") or datetime.utcnow().isoformat()
    content_hash = hashlib.sha256((title + url).encode()).hexdigest()
    return {
        "source": "github",
        "url": url,
        "title": title,
        "description": description,
        "published_at": updated_at,
        "content_hash": content_hash,
    }


async def fetch_new() -> list[dict]:
    """Fetch recently updated AI repos from GitHub Search API."""
    query = _all_keywords()
    params = {
        "q": f"{query} topic:machine-learning",
        "sort": "updated",
        "order": "desc",
        "per_page": 100,
    }
    try:
        async with httpx.AsyncClient(headers=_headers(), timeout=30) as client:
            resp = await client.get(_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
            return [_parse_item(item) for item in data.get("items", [])]
    except Exception as exc:
        logger.warning("GitHub fetch_new failed: %s", exc)
        return []


async def backfill(since: str = "2025-12-01") -> list[dict]:
    """Paginate through repos created since `since` date. Max 10 pages."""
    query = _all_keywords()
    results: list[dict] = []

    async with httpx.AsyncClient(headers=_headers(), timeout=30) as client:
        for page in range(1, 11):
            params = {
                "q": f"{query} topic:machine-learning created:>{since}",
                "sort": "updated",
                "order": "desc",
                "per_page": 100,
                "page": page,
            }
            try:
                resp = await client.get(_BASE, params=params)
                if resp.status_code == 422:
                    logger.info("GitHub backfill: query too long, stopping at page %d", page)
                    break
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                if not items:
                    break
                results.extend(_parse_item(item) for item in items)
                logger.info("GitHub backfill page %d: %d items", page, len(items))
                if len(items) < 100:
                    break
            except Exception as exc:
                logger.warning("GitHub backfill page %d failed: %s", page, exc)
                break

    return results
