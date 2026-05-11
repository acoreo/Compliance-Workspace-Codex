"""SQLite schema definitions and version tracking."""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

_DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS scans (
    scan_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_key     TEXT    NOT NULL,
    root_path     TEXT    NOT NULL,
    mode          TEXT    NOT NULL,
    scan_ts       TEXT    NOT NULL,
    file_count    INTEGER NOT NULL DEFAULT 0,
    folder_count  INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    duration_ms   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS file_nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id     INTEGER NOT NULL REFERENCES scans(scan_id),
    name        TEXT    NOT NULL,
    full_path   TEXT    NOT NULL,
    extension   TEXT    NOT NULL,
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    modified_ts TEXT    NOT NULL,
    depth       INTEGER NOT NULL DEFAULT 0,
    parent_path TEXT    NOT NULL,
    is_document INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS folder_nodes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id            INTEGER NOT NULL REFERENCES scans(scan_id),
    full_path          TEXT    NOT NULL,
    depth              INTEGER NOT NULL DEFAULT 0,
    direct_file_count  INTEGER NOT NULL DEFAULT 0,
    subtree_file_count INTEGER NOT NULL DEFAULT 0,
    doc_count          INTEGER NOT NULL DEFAULT 0,
    is_hotspot         INTEGER,          -- RESERVED: NULL in MVP
    hotspot_signals    TEXT              -- RESERVED: NULL in MVP
);

CREATE TABLE IF NOT EXISTS scan_errors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id    INTEGER NOT NULL REFERENCES scans(scan_id),
    path       TEXT    NOT NULL,
    error_type TEXT    NOT NULL,
    error_msg  TEXT    NOT NULL
);
"""


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all tables and set schema version if not already set."""
    conn.executescript(_DDL)
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
