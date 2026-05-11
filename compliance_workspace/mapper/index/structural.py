"""Structural retrieval via SQL hierarchy traversal.

All functions return typed lists of Chunk objects — no raw cursors
are exposed outside this module.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from mapper.models.chunk import Chunk
from mapper.index.store import _row_to_chunk


def get_requirements_for_standard(
    conn: sqlite3.Connection, standard_id: str
) -> List[Chunk]:
    """Return all requirement chunks for a standard."""
    rows = conn.execute(
        "SELECT * FROM chunks WHERE standard_id = ? AND chunk_type = 'requirement'",
        (standard_id,),
    ).fetchall()
    return [_row_to_chunk(r) for r in rows]


def get_measures_for_requirement(
    conn: sqlite3.Connection, requirement_id: str
) -> List[Chunk]:
    """Return all measure chunks under a requirement."""
    rows = conn.execute(
        "SELECT * FROM chunks WHERE requirement_id = ? AND chunk_type = 'measure'",
        (requirement_id,),
    ).fetchall()
    return [_row_to_chunk(r) for r in rows]


def get_vsl_for_requirement(
    conn: sqlite3.Connection, requirement_id: str
) -> List[Chunk]:
    """Return all VSL artifact chunks for a requirement."""
    rows = conn.execute(
        "SELECT * FROM chunks "
        "WHERE governing_requirement_reference = ? AND chunk_type = 'vsl_artifact'",
        (requirement_id,),
    ).fetchall()
    return [_row_to_chunk(r) for r in rows]


def get_attachments_for_standard(
    conn: sqlite3.Connection, standard_id: str
) -> List[Chunk]:
    """Return all attachment chunks for a standard."""
    rows = conn.execute(
        "SELECT * FROM chunks "
        "WHERE standard_id = ? "
        "  AND chunk_type IN ('attachment_obligation', 'attachment_measure')",
        (standard_id,),
    ).fetchall()
    return [_row_to_chunk(r) for r in rows]


def get_children(conn: sqlite3.Connection, chunk_id: str) -> List[Chunk]:
    """Return direct child chunks (parent_child relationships only)."""
    rows = conn.execute(
        """
        SELECT c.* FROM chunks c
        JOIN chunk_relationships r ON r.child_chunk_id = c.chunk_id
        WHERE r.parent_chunk_id = ? AND r.relationship_type = 'parent_child'
        """,
        (chunk_id,),
    ).fetchall()
    return [_row_to_chunk(r) for r in rows]


def get_full_path(conn: sqlite3.Connection, chunk_id: str) -> str:
    """Return the official_citation_path for a chunk."""
    row = conn.execute(
        "SELECT official_citation_path FROM chunks WHERE chunk_id = ?",
        (chunk_id,),
    ).fetchone()
    return row[0] if row else ""


def get_chunks_by_type(
    conn: sqlite3.Connection, chunk_type: str
) -> List[Chunk]:
    """Return all chunks of a given type."""
    rows = conn.execute(
        "SELECT * FROM chunks WHERE chunk_type = ?",
        (chunk_type,),
    ).fetchall()
    return [_row_to_chunk(r) for r in rows]


def get_definition(conn: sqlite3.Connection, term: str) -> Optional[Chunk]:
    """Return the definition chunk whose text contains *term* (case-insensitive)."""
    row = conn.execute(
        "SELECT * FROM chunks "
        "WHERE chunk_type = 'definition' AND lower(text) LIKE lower(?)",
        (f"%{term}%",),
    ).fetchone()
    return _row_to_chunk(row) if row else None
