"""DB schema extensions for Phase 2 chunk tables.

Adds chunks, chunk_relationships, and vsl_artifacts tables to the
existing workspace.db without touching Phase 1 tables.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

_DDL = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id                        TEXT    PRIMARY KEY,
    scan_id                         INTEGER NOT NULL REFERENCES scans(scan_id),
    file_node_id                    INTEGER NOT NULL REFERENCES file_nodes(id),
    standard_id                     TEXT    NOT NULL DEFAULT '',
    document_title                  TEXT    NOT NULL DEFAULT '',
    chunk_type                      TEXT    NOT NULL,
    official_citation_path          TEXT    NOT NULL DEFAULT '',
    parent_chunk_id                 TEXT,
    requirement_id                  TEXT,
    subrequirement_path             TEXT,
    measure_id                      TEXT,
    attachment_id                   TEXT,
    source_location                 TEXT    NOT NULL DEFAULT '',
    effective_date                  TEXT,
    version                         TEXT,
    applicability_tags              TEXT    NOT NULL DEFAULT '[]',
    governing_requirement_reference TEXT,
    vsl_row_id                      TEXT,
    vsl_level                       TEXT,
    expected_evidence               TEXT    NOT NULL DEFAULT '[]',
    text                            TEXT    NOT NULL DEFAULT '',
    embedding                       BLOB,
    created_ts                      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS chunk_relationships (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_chunk_id   TEXT    NOT NULL REFERENCES chunks(chunk_id),
    child_chunk_id    TEXT    NOT NULL REFERENCES chunks(chunk_id),
    relationship_type TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS vsl_artifacts (
    vsl_id          TEXT    PRIMARY KEY,
    chunk_id        TEXT    NOT NULL REFERENCES chunks(chunk_id),
    standard_id     TEXT    NOT NULL DEFAULT '',
    requirement_ref TEXT    NOT NULL DEFAULT '',
    vsl_level       TEXT    NOT NULL,
    vsl_text        TEXT    NOT NULL DEFAULT '',
    row_id          TEXT    NOT NULL DEFAULT '',
    created_ts      TEXT    NOT NULL
);
"""


def create_chunk_tables(conn: sqlite3.Connection) -> None:
    """Create Phase 2 tables in an existing DB. Safe to call repeatedly."""
    conn.executescript(_DDL)
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
