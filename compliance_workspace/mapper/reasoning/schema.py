"""Phase 3 DB schema: evidence_text, evidence_candidates, evidence_assessments, gap_reports.

Adds Phase 3 tables to the existing workspace.db without touching Phase 1/2 tables.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 4

_DDL = """
CREATE TABLE IF NOT EXISTS email_attachments (
    attachment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    file_node_id      INTEGER NOT NULL REFERENCES file_nodes(id),
    filename          TEXT    NOT NULL,
    extension         TEXT,
    size_bytes        INTEGER,
    text              TEXT,
    extraction_method TEXT,
    error             TEXT,
    extracted_ts      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_text (
    file_node_id      INTEGER PRIMARY KEY REFERENCES file_nodes(id),
    text              TEXT    NOT NULL DEFAULT '',
    extraction_method TEXT    NOT NULL DEFAULT '',
    char_count        INTEGER NOT NULL DEFAULT 0,
    extracted_ts      TEXT    NOT NULL,
    error             TEXT
);

CREATE TABLE IF NOT EXISTS evidence_candidates (
    candidate_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT    NOT NULL,
    chunk_id          TEXT    NOT NULL REFERENCES chunks(chunk_id),
    file_node_id      INTEGER NOT NULL REFERENCES file_nodes(id),
    structural_score  REAL    NOT NULL DEFAULT 0.0,
    semantic_score    REAL    NOT NULL DEFAULT 0.0,
    combined_score    REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS evidence_assessments (
    assessment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT    NOT NULL,
    chunk_id          TEXT    NOT NULL REFERENCES chunks(chunk_id),
    file_node_id      INTEGER NOT NULL REFERENCES file_nodes(id),
    verdict           TEXT    NOT NULL,
    confidence        REAL    NOT NULL DEFAULT 0.0,
    rationale         TEXT    NOT NULL DEFAULT '',
    cited_text        TEXT,
    gaps_identified   TEXT    NOT NULL DEFAULT '[]',
    raw_llm_response  TEXT    NOT NULL DEFAULT '',
    prompt_version    TEXT    NOT NULL DEFAULT '',
    assessed_ts       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gap_reports (
    report_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               TEXT    NOT NULL,
    standard_id          TEXT    NOT NULL,
    generated_ts         TEXT    NOT NULL,
    total_requirements   INTEGER NOT NULL DEFAULT 0,
    satisfied_count      INTEGER NOT NULL DEFAULT 0,
    partial_count        INTEGER NOT NULL DEFAULT 0,
    gap_count            INTEGER NOT NULL DEFAULT 0,
    not_applicable_count INTEGER NOT NULL DEFAULT 0,
    report_json          TEXT    NOT NULL DEFAULT '',
    report_html          TEXT    NOT NULL DEFAULT ''
);
"""


def create_reasoning_tables(conn: sqlite3.Connection) -> None:
    """Create Phase 3 tables in an existing DB. Safe to call repeatedly."""
    conn.executescript(_DDL)
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
