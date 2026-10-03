import sqlite3

from fastapi import Request

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id            TEXT PRIMARY KEY,
    case_hash     TEXT NOT NULL UNIQUE,     -- only the hash, the real code is never saved
    category      TEXT NOT NULL,
    description   TEXT NOT NULL,
    evidence_url  TEXT,
    status        TEXT NOT NULL,
    is_closed     INTEGER NOT NULL DEFAULT 0,
    submitted_on  TEXT NOT NULL             -- date only, no time
);

CREATE TABLE IF NOT EXISTS moderators (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT NOT NULL UNIQUE,
    password_hash    TEXT NOT NULL,
    failed_attempts  INTEGER NOT NULL DEFAULT 0,
    locked_until     TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_updates (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id            TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    moderator_id         INTEGER NOT NULL REFERENCES moderators(id),
    from_status          TEXT,
    to_status            TEXT,
    note                 TEXT NOT NULL,
    visible_to_reporter  INTEGER NOT NULL,
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash    TEXT PRIMARY KEY,
    moderator_id  INTEGER NOT NULL REFERENCES moderators(id) ON DELETE CASCADE,
    expires_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_status   ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_category ON reports(category);
CREATE INDEX IF NOT EXISTS idx_updates_report   ON report_updates(report_id);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_db(request: Request):
    conn = connect(request.app.state.settings.database_path)
    try:
        yield conn
    finally:
        conn.close()
