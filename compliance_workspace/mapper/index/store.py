"""Chunk read/write operations against the chunks, vsl_artifacts,
and chunk_relationships tables.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np

from mapper.models.chunk import Chunk, ChunkMetadata, VSLArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_embedding(arr: np.ndarray) -> bytes:
    return arr.astype(np.float32).tobytes()


def _deserialize_embedding(blob: bytes) -> List[float]:
    return np.frombuffer(blob, dtype=np.float32).tolist()


def _row_to_chunk(row: tuple) -> Chunk:
    (
        chunk_id, scan_id, file_node_id, standard_id, document_title,
        chunk_type, citation_path, parent_chunk_id,
        requirement_id, subrequirement_path, measure_id, attachment_id,
        source_location, effective_date, version, applicability_tags_json,
        gov_req_ref, vsl_row_id, vsl_level,
        expected_evidence_json, text, embedding_blob, _created_ts,
    ) = row

    embedding = _deserialize_embedding(embedding_blob) if embedding_blob else None

    metadata = ChunkMetadata(
        standard_id=standard_id or "",
        document_title=document_title or "",
        chunk_type=chunk_type,
        official_citation_path=citation_path or "",
        parent_chunk_id=parent_chunk_id,
        child_chunk_ids=[],
        requirement_id=requirement_id,
        subrequirement_path=subrequirement_path,
        measure_id=measure_id,
        attachment_id=attachment_id,
        source_location=source_location or "",
        effective_date=effective_date,
        version=version,
        applicability_tags=json.loads(applicability_tags_json or "[]"),
        governing_requirement_reference=gov_req_ref,
        vsl_row_id=vsl_row_id,
        vsl_level=vsl_level,
        expected_evidence=json.loads(expected_evidence_json or "[]"),
    )

    return Chunk(
        chunk_id=chunk_id,
        scan_id=scan_id,
        file_node_id=file_node_id,
        text=text or "",
        metadata=metadata,
        embedding=embedding,
    )


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def write_chunks(conn: sqlite3.Connection, chunks: List[Chunk]) -> None:
    """Batch-insert (or replace) chunks into the chunks table."""
    now = _now_ts()
    rows = []
    for c in chunks:
        m = c.metadata
        emb_blob = (
            _serialize_embedding(np.array(c.embedding, dtype=np.float32))
            if c.embedding is not None
            else None
        )
        rows.append((
            c.chunk_id,
            c.scan_id,
            c.file_node_id,
            m.standard_id,
            m.document_title,
            m.chunk_type,
            m.official_citation_path,
            m.parent_chunk_id,
            m.requirement_id,
            m.subrequirement_path,
            m.measure_id,
            m.attachment_id,
            m.source_location,
            m.effective_date,
            m.version,
            json.dumps(m.applicability_tags),
            m.governing_requirement_reference,
            m.vsl_row_id,
            m.vsl_level,
            json.dumps(m.expected_evidence),
            c.text,
            emb_blob,
            now,
        ))

    conn.executemany(
        """
        INSERT OR REPLACE INTO chunks (
            chunk_id, scan_id, file_node_id, standard_id, document_title,
            chunk_type, official_citation_path, parent_chunk_id,
            requirement_id, subrequirement_path, measure_id, attachment_id,
            source_location, effective_date, version, applicability_tags,
            governing_requirement_reference, vsl_row_id, vsl_level,
            expected_evidence, text, embedding, created_ts
        ) VALUES (
            ?,?,?,?,?,
            ?,?,?,
            ?,?,?,?,
            ?,?,?,?,
            ?,?,?,
            ?,?,?,?
        )
        """,
        rows,
    )
    conn.commit()


def write_vsl_artifacts(
    conn: sqlite3.Connection, artifacts: List[VSLArtifact]
) -> None:
    """Batch-insert (or replace) VSL artifact records."""
    now = _now_ts()
    conn.executemany(
        """
        INSERT OR REPLACE INTO vsl_artifacts
            (vsl_id, chunk_id, standard_id, requirement_ref,
             vsl_level, vsl_text, row_id, created_ts)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        [
            (
                a.vsl_id, a.chunk_id, a.standard_id, a.requirement_ref,
                a.vsl_level, a.vsl_text, a.row_id, now,
            )
            for a in artifacts
        ],
    )
    conn.commit()


def write_relationships(conn: sqlite3.Connection, relationships) -> None:
    """Batch-insert chunk relationships (accepts ChunkRelationship objects)."""
    conn.executemany(
        """
        INSERT OR IGNORE INTO chunk_relationships
            (parent_chunk_id, child_chunk_id, relationship_type)
        VALUES (?,?,?)
        """,
        [
            (r.parent_chunk_id, r.child_chunk_id, r.relationship_type)
            for r in relationships
        ],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def get_chunk(conn: sqlite3.Connection, chunk_id: str) -> Optional[Chunk]:
    """Fetch a single chunk by ID. Returns None if not found."""
    row = conn.execute(
        "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
    ).fetchone()
    return _row_to_chunk(row) if row else None


def update_embedding(
    conn: sqlite3.Connection, chunk_id: str, embedding: np.ndarray
) -> None:
    """Write (or overwrite) the embedding BLOB for a single chunk."""
    conn.execute(
        "UPDATE chunks SET embedding = ? WHERE chunk_id = ?",
        (_serialize_embedding(embedding), chunk_id),
    )
    conn.commit()
