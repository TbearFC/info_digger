import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "./data/info_digger.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init() -> None:
    # Ensure data directory exists (important for Docker bind mount and bare installs)
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source       TEXT NOT NULL,
            url          TEXT NOT NULL,
            title        TEXT NOT NULL,
            summary      TEXT,
            topic_tags   TEXT NOT NULL DEFAULT '[]',
            published_at TEXT NOT NULL,
            fetched_at   TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_published ON entries(published_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON entries(source)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_calls (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            called_at  TEXT NOT NULL,
            caller     TEXT NOT NULL,
            success    INTEGER NOT NULL,
            error_msg  TEXT
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_calls_called_at ON api_calls(called_at)"
    )

    conn.commit()
    conn.close()


def hash_exists(content_hash: str) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM entries WHERE content_hash = ?", (content_hash,)
    ).fetchone()
    conn.close()
    return row is not None


def insert_entry(
    source: str,
    url: str,
    title: str,
    summary: str,
    topic_tags: list[str],
    published_at: str,
    content_hash: str,
) -> None:
    conn = _connect()
    conn.execute(
        """
        INSERT OR IGNORE INTO entries
            (source, url, title, summary, topic_tags, published_at, fetched_at, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            url,
            title,
            summary,
            json.dumps(topic_tags),
            published_at,
            datetime.utcnow().isoformat(),
            content_hash,
        ),
    )
    conn.commit()
    conn.close()


def get_entries(
    topic: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    before: Optional[str] = None,
) -> list[dict]:
    conn = _connect()
    clauses = []
    params: list = []

    if topic:
        clauses.append("topic_tags LIKE ?")
        params.append(f'%"{topic}"%')
    if source:
        clauses.append("source = ?")
        params.append(source)
    if before:
        clauses.append("published_at < ?")
        params.append(before)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params += [limit, offset]

    rows = conn.execute(
        f"SELECT * FROM entries {where} ORDER BY published_at DESC LIMIT ? OFFSET ?",
        params,
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        d = dict(row)
        d["topic_tags"] = json.loads(d["topic_tags"])
        result.append(d)
    return result


def get_topics() -> list[str]:
    conn = _connect()
    rows = conn.execute("SELECT DISTINCT topic_tags FROM entries").fetchall()
    conn.close()

    topics: set[str] = set()
    for row in rows:
        for tag in json.loads(row[0]):
            topics.add(tag)
    return sorted(topics)


def get_stats(topic: Optional[str] = None) -> list[dict]:
    """Return monthly entry counts per source for the activity chart."""
    conn = _connect()
    clauses = ["published_at IS NOT NULL"]
    params: list = []

    if topic:
        clauses.append("topic_tags LIKE ?")
        params.append(f'%"{topic}"%')

    where = "WHERE " + " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT strftime('%Y-%m', published_at) as month, source, COUNT(*) as count
        FROM entries
        {where}
        GROUP BY month, source
        ORDER BY month
        """,
        params,
    ).fetchall()
    conn.close()

    # Pivot to [{month, github, arxiv, huggingface, twitter}, ...]
    months: dict[str, dict] = {}
    for row in rows:
        m = row["month"]
        if m not in months:
            months[m] = {"month": m}
        months[m][row["source"]] = row["count"]

    return list(months.values())


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def get_digest_entries(hours: int = 24) -> list[dict]:
    """Return entries published within the last `hours` hours, newest first."""
    from datetime import timedelta
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM entries WHERE published_at >= ? ORDER BY published_at DESC LIMIT 200",
        (since,),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["topic_tags"] = json.loads(d["topic_tags"])
        result.append(d)
    return result


def log_api_call(caller: str, success: bool, error_msg: Optional[str] = None) -> None:
    """Record a Claude API call for health monitoring."""
    conn = _connect()
    conn.execute(
        "INSERT INTO api_calls (called_at, caller, success, error_msg) VALUES (?, ?, ?, ?)",
        (
            datetime.utcnow().isoformat(),
            caller,
            1 if success else 0,
            error_msg,
        ),
    )
    conn.commit()
    conn.close()


def get_health() -> dict:
    """Aggregate data for GET /admin/health."""
    conn = _connect()

    total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    last_crawl_row = conn.execute(
        "SELECT MAX(fetched_at) FROM entries"
    ).fetchone()
    last_crawl_at = last_crawl_row[0] if last_crawl_row else None

    # Per-source stats (today = UTC calendar day)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    source_rows = conn.execute(
        """
        SELECT source,
               MAX(fetched_at) as last_crawl_at,
               SUM(CASE WHEN fetched_at >= ? THEN 1 ELSE 0 END) as entries_today
        FROM entries
        GROUP BY source
        """,
        (today,),
    ).fetchall()

    sources: dict = {}
    for r in source_rows:
        sources[r["source"]] = {
            "last_crawl_at": r["last_crawl_at"],
            "entries_today": r["entries_today"],
            "status": "ok",
        }

    # Always include all known sources
    for src in ("github", "arxiv", "huggingface", "twitter"):
        if src not in sources:
            sources[src] = {
                "last_crawl_at": None,
                "entries_today": 0,
                "status": "disabled",
            }

    # Claude API stats (rolling 24h)
    since_24h = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
    api_rows = conn.execute(
        "SELECT success, error_msg FROM api_calls WHERE called_at >= ?",
        (since_24h,),
    ).fetchall()

    calls_total = len(api_rows)
    calls_ok = sum(1 for r in api_rows if r["success"])
    last_error = next(
        (r["error_msg"] for r in reversed(api_rows) if not r["success"]), None
    )

    conn.close()

    return {
        "last_crawl_at": last_crawl_at,
        "total_entries": total,
        "sources": sources,
        "claude_api": {
            "calls_last_24h": calls_total,
            "success_rate": round(calls_ok / calls_total, 4) if calls_total else None,
            "last_error": last_error,
        },
    }
