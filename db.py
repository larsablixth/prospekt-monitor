"""
db.py — SQLite-hantering för deduplicering och spårning av dokument.
"""

import sqlite3
from datetime import datetime


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id          TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            company     TEXT,
            doc_type    TEXT,
            url         TEXT,
            local_path  TEXT,
            first_seen  TEXT NOT NULL,
            analyzed    INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            doc_id          TEXT NOT NULL,
            provider        TEXT NOT NULL,
            score           INTEGER,
            verdict         TEXT,
            summary         TEXT,
            full_json       TEXT,
            created_at      TEXT NOT NULL,
            PRIMARY KEY (doc_id, provider)
        )
    """)
    conn.commit()
    return conn


def is_new(conn: sqlite3.Connection, doc_id: str) -> bool:
    cur = conn.execute("SELECT 1 FROM documents WHERE id = ?", (doc_id,))
    return cur.fetchone() is None


def save_document(conn: sqlite3.Connection, doc: dict):
    conn.execute(
        """INSERT OR IGNORE INTO documents
           (id, source, company, doc_type, url, local_path, first_seen)
           VALUES (:id, :source, :company, :doc_type, :url, :local_path, :first_seen)""",
        {**doc, "first_seen": datetime.now().isoformat()},
    )
    conn.commit()


def save_analysis(conn: sqlite3.Connection, doc_id: str, provider: str, result: dict):
    import json
    conn.execute(
        """INSERT OR REPLACE INTO analyses
           (doc_id, provider, score, verdict, summary, full_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            doc_id,
            provider,
            result.get("total_score"),
            result.get("verdict"),
            result.get("summary"),
            json.dumps(result, ensure_ascii=False),
            datetime.now().isoformat(),
        ),
    )
    conn.execute("UPDATE documents SET analyzed = 1 WHERE id = ?", (doc_id,))
    conn.commit()


def get_analyses(conn: sqlite3.Connection, doc_id: str) -> list:
    cur = conn.execute(
        "SELECT provider, score, verdict, summary, full_json FROM analyses WHERE doc_id = ?",
        (doc_id,),
    )
    return cur.fetchall()
