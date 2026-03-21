import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

import db
from pipeline import run_backfill, run_crawl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    logger.info("Database initialized")

    # Run backfill once if not already done
    if not os.getenv("DB_BACKFILLED"):
        asyncio.create_task(_run_backfill_and_mark())
    else:
        # Always do a fresh crawl on startup
        asyncio.create_task(run_crawl())

    scheduler.add_job(run_crawl, "interval", minutes=60, id="crawl")
    scheduler.start()
    logger.info("Scheduler started (hourly crawl)")

    yield

    scheduler.shutdown()


async def _run_backfill_and_mark():
    await run_backfill()
    # Mark backfill as done by writing to a sentinel file
    # (env var can't be set persistently at runtime, so use a file)
    Path(".backfilled").touch()
    logger.info("Backfill complete — set DB_BACKFILLED=1 in .env to skip on next restart")


# Check for sentinel file on import
if Path(".backfilled").exists():
    os.environ["DB_BACKFILLED"] = "1"

app = FastAPI(title="info_digger", lifespan=lifespan)


# ── Entries & topics ────────────────────────────────────────────────────────

@app.get("/api/entries")
async def api_entries(
    topic: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    before: Optional[str] = Query(None),
):
    entries = db.get_entries(
        topic=topic, source=source, limit=limit, offset=offset, before=before
    )
    return JSONResponse(entries)


@app.get("/api/topics")
async def api_topics():
    return JSONResponse(db.get_topics())


# ── Activity stats (for SVG chart) ──────────────────────────────────────────

@app.get("/api/stats")
async def api_stats(topic: Optional[str] = Query(None)):
    return JSONResponse(db.get_stats(topic=topic))


# ── Health monitoring ────────────────────────────────────────────────────────

@app.get("/admin/health")
async def admin_health():
    return JSONResponse(db.get_health())


# ── Research assistant ───────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    topic: Optional[str] = None


@app.post("/api/ask")
async def api_ask(req: AskRequest):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail={"error": "service_unavailable", "message": "ANTHROPIC_API_KEY not configured"},
        )

    # Fetch context entries
    entries = db.get_entries(topic=req.topic, limit=50)

    # Build context string with token budget (~7000 tokens max)
    context_parts = []
    approx_tokens = 0
    limit = 50 if not entries else (30 if len(entries) > 30 else 50)

    for e in entries[:limit]:
        desc = (e.get("description") or e.get("summary") or "")[:300]
        line = f"[{e['source']}] {e['title']}: {desc}"
        approx_tokens += len(line) // 4
        if approx_tokens > 7000:
            break
        context_parts.append(line)

    context = "\n".join(context_parts) if context_parts else "(暂无数据)"

    system_prompt = (
        "你是一个AI领域情报分析师。根据以下从各平台（GitHub、arXiv、HuggingFace等）收集的最新数据，"
        "用中文简洁回答用户问题。如无相关数据，直接说明。"
    )
    if not context_parts:
        system_prompt += " 当前暂无收集到的数据，请直接说明无法作答。"

    user_message = f"数据：\n{context}\n\n问题：{req.question}"

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        message = await client.messages.create(
            model=model,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        answer = message.content[0].text.strip()
        db.log_api_call("ask", success=True)
    except Exception as exc:
        logger.warning("ask failed: %s", exc)
        db.log_api_call("ask", success=False, error_msg=str(exc))
        raise HTTPException(
            status_code=503,
            detail={"error": "service_unavailable", "message": str(exc)},
        )

    sources = [
        {
            "title": e["title"],
            "url": e["url"],
            "source": e["source"],
            "published_at": e["published_at"],
        }
        for e in entries[:limit]
    ]
    return JSONResponse({"answer": answer, "sources": sources})


# ── Static files ─────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
