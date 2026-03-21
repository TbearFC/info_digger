import hashlib
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://huggingface.co/api/models?sort=lastModified&direction=-1&limit=100"


async def fetch_new() -> list[dict]:
    """Fetch the 100 most recently modified HuggingFace models."""
    headers = {}
    token = os.getenv("HF_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(_API_URL, headers=headers)
            resp.raise_for_status()
            items = resp.json()
    except Exception as exc:
        logger.warning("HuggingFace fetch failed: %s", exc)
        return []

    results = []
    for item in items:
        model_id = item.get("modelId", "")
        if not model_id:
            continue

        url = f"https://huggingface.co/{model_id}"

        tags = item.get("tags", [])
        pipeline_tag = item.get("pipeline_tag", "")
        description = ", ".join([t for t in tags + [pipeline_tag] if t])

        # Strip milliseconds and timezone from ISO8601 timestamp
        last_modified = item.get("lastModified", "")
        published_at = last_modified.replace("Z", "").split(".")[0] if last_modified else ""

        content_hash = hashlib.sha256(model_id.encode()).hexdigest()

        results.append({
            "source": "huggingface",
            "url": url,
            "title": model_id,
            "description": description,
            "published_at": published_at,
            "content_hash": content_hash,
        })

    logger.info("HuggingFace fetch: %d models", len(results))
    return results
