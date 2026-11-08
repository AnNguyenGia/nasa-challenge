import sqlite3
from contextlib import contextmanager
from app.core import config

@contextmanager
def connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA foreign_keys=ON")
    try:
        with db:
            yield db
    finally:
        db.close()

def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version VALUES(1);
        CREATE TABLE IF NOT EXISTS readings(
          id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL,
          observed_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
          id TEXT PRIMARY KEY, type TEXT NOT NULL, payload TEXT NOT NULL,
          created_at TEXT NOT NULL, processed INTEGER NOT NULL DEFAULT 0,
          synced INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
          retry_at REAL NOT NULL DEFAULT 0, dead_letter INTEGER NOT NULL DEFAULT 0,
          last_error TEXT);
        CREATE TABLE IF NOT EXISTS assessments(
          reading_id TEXT PRIMARY KEY REFERENCES readings(id),
          payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS event_pending ON events(processed, synced, retry_at);
        """)
