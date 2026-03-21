import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "./info_digger.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init() -> None:
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
