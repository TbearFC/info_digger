import logging
import os
from typing import Optional

import anthropic

import db

logger = logging.getLogger(__name__)

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


async def summarize(title: str, description: str) -> str:
    """Return a 1-sentence summary. Returns empty string on any error."""
    if not title and not description:
        return ""
    try:
        client = _get_client()
        message = await client.messages.create(
            model=_model(),
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize in one concise sentence what this AI project or paper is about.\n"
                        f"Title: {title}\n"
                        f"Description: {description or '(none)'}"
                    ),
                }
            ],
        )
        db.log_api_call("summarizer", success=True)
        return message.content[0].text.strip()
    except Exception as exc:
        logger.warning("summarize failed for %r: %s", title, exc)
        db.log_api_call("summarizer", success=False, error_msg=str(exc))
        return ""
