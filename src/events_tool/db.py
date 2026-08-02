"""SQLite connection and schema management.

Events and the ingestion audit log are relational/queryable data, so they
live in SQLite (data/events.db) rather than the JSON profile. Schema is
created idempotently with CREATE TABLE IF NOT EXISTS so `events init` and
every CLI invocation can safely call get_connection() without a separate
migration step.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "events.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'uncategorized',
    start_dt TEXT NOT NULL,
    end_dt TEXT,
    location_name TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    neighborhood TEXT NOT NULL DEFAULT '',
    lat REAL,
    lon REAL,
    url TEXT NOT NULL DEFAULT '',
    source_name TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    external_uid TEXT NOT NULL DEFAULT '',
    dedup_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'candidate',
    roundup_included_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_start_dt ON events(start_dt);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    run_at TEXT NOT NULL,
    items_found INTEGER NOT NULL DEFAULT 0,
    items_added INTEGER NOT NULL DEFAULT 0,
    items_deduped INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ok',
    notes TEXT NOT NULL DEFAULT ''
);
"""


def get_connection(path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
