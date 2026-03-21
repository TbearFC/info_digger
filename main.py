import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


# Mount static files (CSS, JS if ever split out)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
